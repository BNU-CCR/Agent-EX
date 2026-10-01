"""New study identities deliberately separate from legacy 12-cell contracts."""

from dataclasses import dataclass


STUDY_ID = "paper1.identity-network.v1"


@dataclass(frozen=True, slots=True)
class StudyCell:
    cell_id: str
    salience: str
    network: str

    def __post_init__(self):
        saliences = ("blind", "salient")
        networks = ("no_social", "randomized", "clustered_ws")
        if self.salience not in saliences or self.network not in networks:
            raise ValueError("unknown study factor")
        expected = f"SIS-A{saliences.index(self.salience)}-B{networks.index(self.network)}"
        if self.cell_id != expected:
            raise ValueError("cell identity does not match factors")


def study_cells() -> tuple[StudyCell, ...]:
    return tuple(
        StudyCell(f"SIS-A{a}-B{b}", salience, network)
        for a, salience in enumerate(("blind", "salient"))
        for b, network in enumerate(("no_social", "randomized", "clustered_ws"))
    )
