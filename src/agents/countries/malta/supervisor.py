"""Country Supervisor dla Malta (MT).

Zarzadza agentami zbierajacymi dane z Malta: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class MTSupervisor(CountrySupervisor):
    """Supervisor agentow dla Malta."""

    def __init__(self):
        super().__init__(country_code="MT", config_path=CONFIG_PATH)
        self.load_config()
