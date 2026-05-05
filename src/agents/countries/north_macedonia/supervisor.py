"""Country Supervisor dla North Macedonia (MK).

Zarzadza agentami zbierajacymi dane z North Macedonia: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class MKSupervisor(CountrySupervisor):
    """Supervisor agentow dla North Macedonia."""

    def __init__(self):
        super().__init__(country_code="MK", config_path=CONFIG_PATH)
        self.load_config()
