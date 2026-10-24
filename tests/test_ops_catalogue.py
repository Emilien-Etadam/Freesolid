"""Le catalogue engine/ops/ : pur, sans doublon, cohérent avec le noyau."""

from engine import ops, protocol
from engine.kernel import Kernel


def test_chaque_op_du_noyau_vient_du_catalogue():
    assert sorted(protocol.CORE_OP_NAMES) == sorted(ops.BY_NAME)


def test_chaque_op_a_sa_methode_dans_le_noyau():
    """``dispatch`` appelle ``getattr(kernel, op)`` — sauf ``progress``,
    que le serveur sert lui-même sans prendre le verrou du noyau."""
    sans_methode = [op.name for op in ops.CORE_OPS
                    if not callable(getattr(Kernel, op.name, None))]
    assert sans_methode == ["progress"]


def test_un_apercu_porte_sur_une_op_annulable():
    assert sorted(op.name for op in ops.CORE_OPS
                  if op.preview and not op.undo) == []


def test_une_op_rejouable_dit_ce_qu_elle_cree():
    for op in ops.CORE_OPS:
        if op.replay is not None or op.indexed:
            assert op.creates.startswith("PartDesign::"), op.name
            assert op.name.startswith("add_"), op.name


def test_un_typeid_n_est_recree_que_par_une_op():
    createurs = [op.creates for op in ops.CORE_OPS if op.replay is not None]
    assert len(createurs) == len(set(createurs))


def test_chaque_add_se_rejoue_ou_dit_pourquoi():
    """Une op ``add_*`` crée une fonction ou un objet de l'arbre : elle a
    ``replay=`` ou ``no_replay="raison"``, jamais les deux, jamais aucun."""
    incomplets = [op.name for op in ops.CORE_OPS if op.name.startswith("add_")
                  and (op.replay is None) == (not op.no_replay)]
    assert incomplets == []
    hors_add = [op.name for op in ops.CORE_OPS
                if op.no_replay and not op.name.startswith("add_")]
    assert hors_add == []


def test_raisons_d_accord_avec_le_tableau_fige_du_rejeu():
    """``replay.UNREPLAYABLE_OPS`` reste figé (il sort dans le selftest,
    ``n9_spike_rapport``) ; le catalogue en reprend les raisons mot pour
    mot et n'en contredit aucune."""
    from engine import replay
    for name, raison in replay.UNREPLAYABLE_OPS.items():
        assert ops.NO_REPLAY.get(name) == raison, name
