from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from agente import plantao
from agente.plantao import AGENDA_PADRAO, Execucao, decidir

BRT = ZoneInfo("America/Sao_Paulo")
QUARTA = (2026, 11, 25)


def h(hm, dia=QUARTA):
    hh, mm = map(int, hm.split(":"))
    return datetime(*dia, hh, mm, tzinfo=BRT)


def ex(hm, conclusao="success", dia=QUARTA):
    return Execucao(criada=h(hm, dia), conclusao=conclusao)


def test_agenda_do_dia_util():
    assert decidir(h("07:00"), [], [], AGENDA_PADRAO) == ([], True)                   # cedo: só espera
    assert decidir(h("08:41"), [], [], AGENDA_PADRAO)[0] == [("relatorio.yml", {"turno": "abertura"})]
    assert decidir(h("08:50"), [ex("08:41")], [], AGENDA_PADRAO)[0] == []             # já saiu
    assert decidir(h("09:07"), [ex("08:41")], [], AGENDA_PADRAO)[0] == [("monitor.yml", {})]
    assert decidir(h("09:20"), [ex("08:41")], [ex("09:07")], AGENDA_PADRAO)[0] == []
    assert decidir(h("09:26"), [ex("08:41")], [ex("09:07")], AGENDA_PADRAO)[0] == []
    assert decidir(h("09:27"), [ex("08:41")], [ex("09:07")], AGENDA_PADRAO)[0] == [("monitor.yml", {})]
    assert decidir(h("10:15"), [ex("08:41")], [ex("09:27")], AGENDA_PADRAO)[0] == [("monitor.yml", {})]  # recupera a vez perdida


def test_boletim_perdido_sai_atrasado_mas_nao_tarde_demais():
    rel = [ex("08:41")]
    assert decidir(h("14:40"), rel, [ex("14:30")], AGENDA_PADRAO)[0] == [("relatorio.yml", {"turno": "meio_dia"})]
    assert decidir(h("16:00"), rel, [ex("15:50")], AGENDA_PADRAO)[0] == []            # passou da tolerância
    assert decidir(h("14:40"), rel + [ex("13:17", "cancelled")], [ex("14:30")], AGENDA_PADRAO)[0][0][0] == "relatorio.yml"
    assert decidir(h("14:40"), rel + [ex("13:05")], [ex("14:30")], AGENDA_PADRAO)[0] == []  # botão do painel às 13:05 vale


def test_fim_do_dia_e_fim_de_semana():
    tudo = [ex("08:41"), ex("13:17"), ex("19:43")]
    assert decidir(h("19:50"), tudo, [ex("19:47")], AGENDA_PADRAO) == ([], False)
    sabado = (2026, 11, 28)
    assert decidir(h("10:00", sabado), [], [], AGENDA_PADRAO) == ([], False)
    domingo = (2026, 11, 29)
    assert decidir(h("15:00", domingo), [], [], AGENDA_PADRAO) == ([], True)
    assert decidir(h("17:12", domingo), [], [], AGENDA_PADRAO)[0] == [("relatorio.yml", {"turno": "fim_de_semana"})]


def test_horario_sem_aspas_no_yaml():
    assert plantao._hm(797) == (13, 17) and plantao._hm("08:41") == (8, 41)


class ApiFalsa:
    def __init__(self, ativos=()):
        self.disparos, self.ativos = [], list(ativos)

    def execucoes(self, workflow, desde=None, status=None):
        if workflow == "plantao.yml":
            return self.ativos
        return [Execucao(criada=c) for wf, _, c in self.disparos if wf == workflow]

    def disparar(self, workflow, inputs=None):
        self.disparos.append((workflow, inputs, RELOGIO[0].astimezone(BRT)))


RELOGIO = [None]


def _rodar(inicio_brt, api, **kw):
    RELOGIO[0] = inicio_brt.astimezone(timezone.utc)

    def dormir(s):
        RELOGIO[0] += timedelta(seconds=s)
    motivo = plantao.executar(api, AGENDA_PADRAO, relogio=lambda: RELOGIO[0], dormir=dormir, **kw)
    return motivo, RELOGIO[0].astimezone(BRT)


def test_plantao_dispara_na_hora_e_passa_o_turno():
    api = ApiFalsa()
    motivo, fim = _rodar(h("06:13"), api, meu_id=10)
    assert motivo == "sucessor" and fim < h("11:45")                    # 330 min de job, depois passa adiante
    tipos = [(wf, (i or {}).get("turno")) for wf, i, _ in api.disparos]
    assert tipos[0] == ("relatorio.yml", "abertura") and api.disparos[0][2] == h("08:41")
    assert tipos[-1] == ("plantao.yml", None) and api.disparos[-1][1] == {"sucessor": "true"}
    monitores = [c for wf, _, c in api.disparos if wf == "monitor.yml"]
    assert monitores[0] == h("09:07") and len(monitores) == 8               # 09:07 … 11:27, a cada 20 min
    assert all(b - a == timedelta(minutes=20) for a, b in zip(monitores, monitores[1:]))


def test_plantao_da_tarde_encerra_com_a_agenda():
    api = ApiFalsa()
    motivo, fim = _rodar(h("15:00"), api, meu_id=10)
    assert motivo == "fim_do_dia" and h("19:47") <= fim <= h("19:52")
    assert ("relatorio.yml", {"turno": "fechamento"}, h("19:43")) in api.disparos
    assert ("relatorio.yml", {"turno": "meio_dia"}, h("15:00")) in api.disparos      # o das 13:17 tinha ficado para trás
    assert not any(wf == "plantao.yml" for wf, _, _ in api.disparos)


def test_um_plantao_por_vez():
    api = ApiFalsa(ativos=[Execucao(criada=h("06:13"), status="in_progress", id=5)])
    assert _rodar(h("09:13"), api, meu_id=10)[0] == "ja_ativo" and api.disparos == []
    # o sucessor espera o anterior encerrar em vez de desistir
    api = ApiFalsa(ativos=[Execucao(criada=h("06:13"), status="in_progress", id=5)])
    chamadas = {"n": 0}
    original = api.execucoes

    def execucoes(workflow, desde=None, status=None):
        if workflow == "plantao.yml":
            chamadas["n"] += 1
            return api.ativos if chamadas["n"] == 1 else []
        return original(workflow, desde, status)
    api.execucoes = execucoes
    motivo, _ = _rodar(h("17:00"), api, meu_id=10, sucessor=True)
    assert motivo == "fim_do_dia" and any(wf == "monitor.yml" for wf, _, _ in api.disparos)


def test_workflow_pausado_nao_derruba_o_plantao():
    import urllib.error

    class ApiMonitorPausado(ApiFalsa):
        def disparar(self, workflow, inputs=None):
            if workflow == "monitor.yml":
                raise urllib.error.HTTPError("u", 422, "Workflow is disabled", {}, None)
            super().disparar(workflow, inputs)
    api = ApiMonitorPausado()
    motivo, _ = _rodar(h("15:00"), api, meu_id=10)
    assert motivo == "fim_do_dia"                                     # seguiu até o fim do dia
    assert [i["turno"] for wf, i, _ in api.disparos if wf == "relatorio.yml"] == ["meio_dia", "fechamento"]
