"""Country Supervisor dla Portugal (PT).

Zarzadza agentami zbierajacymi dane z Portugal: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class PTSupervisor(CountrySupervisor):
    """Supervisor agentow dla Portugal."""

    def __init__(self):
        super().__init__(country_code="PT", config_path=CONFIG_PATH)
        self.load_config()
