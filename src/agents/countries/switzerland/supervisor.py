"""Country Supervisor dla Switzerland (CH).

Zarzadza agentami zbierajacymi dane z Switzerland: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class CHSupervisor(CountrySupervisor):
    """Supervisor agentow dla Switzerland."""

    def __init__(self):
        super().__init__(country_code="CH", config_path=CONFIG_PATH)
        self.load_config()
