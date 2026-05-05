"""Country Supervisor dla Austria (AT).

Zarzadza agentami zbierajacymi dane z Austria: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class ATSupervisor(CountrySupervisor):
    """Supervisor agentow dla Austria."""

    def __init__(self):
        super().__init__(country_code="AT", config_path=CONFIG_PATH)
        self.load_config()
