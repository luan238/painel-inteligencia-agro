"""Plantão — a agenda do agente sem depender do agendador do GitHub.

O "schedule" do GitHub Actions atrasa execuções em horas e descarta muitas delas
(o monitor marcado para cada 20 min rodava 1 ou 2 vezes por dia). Já o disparo
manual (workflow_dispatch) começa na hora. Por isso:

  • o workflow plantao.yml é acordado várias vezes por dia pelo agendador — basta
    UM desses chamados funcionar;
  • o plantão fica ativo durante o dia e dispara, por workflow_dispatch, o monitor
    de cotações e os boletins completos nos horários da agenda
    (config/configuracoes.yaml → agenda); um horário perdido é recuperado depois,
    dentro da tolerância;
  • um job do GitHub dura no máximo 6 h: antes disso o plantão passa o turno para
    uma nova execução dele mesmo;
  • só existe um plantão por vez: um chamado que encontra outro ativo encerra em segundos.

Uso (dentro do GitHub Actions): python -m agente.plantao [--sucessor]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

AGENDA_PADRAO = {
    "fuso": "America/Sao_Paulo",
    "relatorios": {                                   # horário → turno do boletim completo
        "dias_uteis": {"08:41": "abertura", "13:17": "meio_dia", "19:43": "fechamento"},
        "sabado": {},
        "domingo": {"17:11": "fim_de_semana"},
    },
    "monitor": {"inicio": "09:07", "fim": "19:47", "intervalo_min": 20},   # só em dias úteis
    "tolerancia_relatorio_min": 150,    # boletim perdido ainda sai se o atraso for menor que isso
    "duracao_max_min": 330,             # depois disso passa o plantão adiante (limite do GitHub: 6 h)
}

WF_RELATORIO, WF_MONITOR, WF_PLANTAO = "relatorio.yml", "monitor.yml", "plantao.yml"


@dataclass
class Execucao:
    criada: datetime            # com fuso
    status: str = "completed"
    conclusao: str | None = "success"
    id: int = 0


# ------------------------------------------------------------------ agenda
_SUBSTITUIR = {"dias_uteis", "sabado", "domingo"}     # listas de horários: a do usuário substitui a padrão


def _mesclar(base: dict, extra: dict) -> dict:
    r = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(r.get(k), dict) and k not in _SUBSTITUIR:
            r[k] = _mesclar(r[k], v)
        else:
            r[k] = v
    return r


def carregar_agenda(raiz: Path) -> dict:
    import yaml
    arq = Path(raiz) / "config" / "configuracoes.yaml"
    dados = yaml.safe_load(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    return _mesclar(AGENDA_PADRAO, (dados or {}).get("agenda") or {})


def _hm(texto) -> tuple[int, int]:
    if isinstance(texto, int):                  # YAML lê 13:17 sem aspas como 797 (minutos)
        return divmod(texto, 60)
    h, m = str(texto).strip().split(":")
    return int(h), int(m)


def _no_dia(dia: date, hm: str, tz: ZoneInfo) -> datetime:
    return datetime(dia.year, dia.month, dia.day, *_hm(hm), tzinfo=tz)


def relatorios_do_dia(dia: date, agenda: dict) -> list[tuple[datetime, str]]:
    tz = ZoneInfo(agenda["fuso"])
    chave = "dias_uteis" if dia.weekday() < 5 else ("sabado" if dia.weekday() == 5 else "domingo")
    tabela = agenda["relatorios"].get(chave) or {}
    return sorted((_no_dia(dia, h, tz), turno) for h, turno in tabela.items())


def janela_monitor(dia: date, agenda: dict) -> tuple[datetime, datetime] | None:
    mon = agenda.get("monitor") or {}
    if dia.weekday() >= 5 or not mon.get("inicio") or not mon.get("fim"):
        return None
    tz = ZoneInfo(agenda["fuso"])
    return _no_dia(dia, mon["inicio"], tz), _no_dia(dia, mon["fim"], tz)


def _validas(execs: list[Execucao]) -> list[Execucao]:
    return [e for e in execs if e.conclusao not in ("cancelled", "skipped")]


def decidir(agora: datetime, rel: list[Execucao], mon: list[Execucao], agenda: dict) -> tuple[list[tuple[str, dict]], bool]:
    """O que disparar agora e se ainda há algo da agenda pela frente hoje.

    agora: horário com fuso. rel/mon: execuções recentes do relatório e do monitor (qualquer origem:
    plantão, botão do painel ou manual)."""
    agora = agora.astimezone(ZoneInfo(agenda["fuso"]))
    acoes: list[tuple[str, dict]] = []
    pela_frente = False
    tol = timedelta(minutes=int(agenda["tolerancia_relatorio_min"]))
    rel = _validas(rel)
    atrasado = None
    for horario, turno in relatorios_do_dia(agora.date(), agenda):
        if horario > agora:
            pela_frente = True
            continue
        feito = any(e.criada >= horario - timedelta(minutes=25) for e in rel)
        if not feito and agora < horario + tol:
            atrasado = turno                       # se houver mais de um, vale o mais recente
    if atrasado:
        acoes.append((WF_RELATORIO, {"turno": atrasado}))

    janela = janela_monitor(agora.date(), agenda)
    if janela:
        ini, fim = janela
        if agora < fim:
            pela_frente = True
        if ini <= agora <= fim + timedelta(minutes=2) and not acoes:
            intervalo = timedelta(minutes=int(agenda["monitor"].get("intervalo_min", 20)))
            vez = ini + ((min(agora, fim) - ini) // intervalo) * intervalo     # 09:07, 09:27, 09:47…
            if not any(e.criada >= vez - timedelta(minutes=2) for e in _validas(mon)):
                acoes.append((WF_MONITOR, {}))
    return acoes, pela_frente


# ------------------------------------------------------------------ GitHub
class GitHub:
    def __init__(self, repo: str, token: str, ref: str = "main"):
        self.repo, self.token, self.ref = repo, token, ref

    def _req(self, metodo: str, caminho: str, corpo: dict | None = None):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{self.repo}/{caminho}", method=metodo,
            data=json.dumps(corpo).encode() if corpo is not None else None,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "agro-intel-plantao",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            texto = r.read()
        return json.loads(texto) if texto else {}

    def execucoes(self, workflow: str, desde: datetime | None = None, status: str | None = None) -> list[Execucao]:
        params = {"per_page": "100"}
        if desde:
            params["created"] = ">=" + desde.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if status:
            params["status"] = status
        dados = self._req("GET", f"actions/workflows/{workflow}/runs?" + urllib.parse.urlencode(params))
        return [Execucao(criada=datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")), status=r.get("status", ""),
                         conclusao=r.get("conclusion"), id=int(r.get("id", 0))) for r in dados.get("workflow_runs", [])]

    def disparar(self, workflow: str, inputs: dict | None = None) -> None:
        corpo = {"ref": self.ref}
        if inputs:
            corpo["inputs"] = {k: str(v) for k, v in inputs.items()}
        self._req("POST", f"actions/workflows/{workflow}/dispatches", corpo)


# ------------------------------------------------------------------ laço
def _log(msg: str, agenda: dict, quando: datetime | None = None) -> None:
    quando = (quando or datetime.now(timezone.utc)).astimezone(ZoneInfo(agenda["fuso"]))
    print(f"[{quando:%d/%m %H:%M:%S}] {msg}", flush=True)


def executar(api, agenda: dict, meu_id: int = 0, sucessor: bool = False,
             relogio=lambda: datetime.now(timezone.utc), dormir=time.sleep) -> str:
    """Roda o plantão até a agenda do dia acabar ou o tempo do job chegar ao fim. Devolve o motivo."""
    tz = ZoneInfo(agenda["fuso"])

    def log(msg):
        _log(msg, agenda, relogio())
    # 1) um plantão por vez: o mais antigo fica; um sucessor espera o anterior terminar
    for tentativa in range(8):
        ativos = [e for e in api.execucoes(WF_PLANTAO, status="in_progress") if e.id != meu_id]
        mais_antigos = [e for e in ativos if not meu_id or e.id < meu_id]
        if not mais_antigos:
            break
        if not sucessor:
            log(f"Já existe um plantão ativo (execução {mais_antigos[0].id}). Nada a fazer.")
            return "ja_ativo"
        log("Aguardando o plantão anterior encerrar…")
        dormir(45)
    else:
        log("O plantão anterior não encerrou; este fica de reserva e termina.")
        return "ja_ativo"

    inicio = relogio()
    limite = inicio + timedelta(minutes=int(agenda["duracao_max_min"]))
    disparados: dict[str, list[Execucao]] = {WF_RELATORIO: [], WF_MONITOR: []}
    erros_seguidos = 0
    log("Plantão iniciado.")
    while True:
        agora = relogio().astimezone(tz)
        try:
            inicio_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)
            rel = api.execucoes(WF_RELATORIO, desde=inicio_dia) + disparados[WF_RELATORIO]
            mon = api.execucoes(WF_MONITOR, desde=agora - timedelta(hours=2)) + disparados[WF_MONITOR]
            acoes, pela_frente = decidir(agora, rel, mon, agenda)
            for wf, inputs in acoes:
                api.disparar(wf, inputs)
                disparados[wf].append(Execucao(criada=agora, status="queued", conclusao=None))
                log(f"Disparado: {wf} {inputs or ''}".rstrip())
            erros_seguidos = 0
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            erros_seguidos += 1
            log(f"Falha ao falar com o GitHub ({e}); tento de novo em 1 min.")
            if erros_seguidos >= 15:
                return "erro_api"
            pela_frente = True
        if not pela_frente:
            log("Agenda do dia concluída. Plantão encerrado.")
            return "fim_do_dia"
        if relogio() + timedelta(minutes=2) >= limite:
            try:
                api.disparar(WF_PLANTAO, {"sucessor": "true"})
                log("Tempo máximo deste job: plantão passado para uma nova execução.")
            except (urllib.error.URLError, OSError) as e:
                log(f"Não consegui passar o plantão adiante ({e}); o próximo chamado agendado retoma.")
            return "sucessor"
        dormir(60 - relogio().second % 60 or 60)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agente.plantao")
    ap.add_argument("--sucessor", action="store_true", help="execução que recebe o plantão de outra")
    args = ap.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("Defina GITHUB_REPOSITORY e GH_TOKEN (o workflow plantao.yml já faz isso).", file=sys.stderr)
        return 2
    raiz = Path(__file__).resolve().parent.parent
    agenda = carregar_agenda(raiz)
    api = GitHub(repo, token, os.environ.get("GITHUB_REF_NAME") or "main")
    motivo = executar(api, agenda, meu_id=int(os.environ.get("GITHUB_RUN_ID") or 0), sucessor=args.sucessor)
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        textos = {"ja_ativo": "Já havia um plantão ativo — este chamado encerrou sem fazer nada (normal).",
                  "fim_do_dia": "Agenda do dia concluída.",
                  "sucessor": "Plantão passado para uma nova execução (limite de 6 h por job do GitHub).",
                  "erro_api": "O GitHub não respondeu por 15 min; o próximo chamado agendado retoma o plantão."}
        with open(resumo, "a", encoding="utf-8") as f:
            f.write(f"### 🕒 Plantão\n\n{textos.get(motivo, motivo)}\n")
    return 1 if motivo == "erro_api" else 0


if __name__ == "__main__":
    sys.exit(main())
