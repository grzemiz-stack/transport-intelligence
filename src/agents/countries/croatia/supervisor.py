"""Country Supervisor dla Croatia (HR).

Zarzadza agentami zbierajacymi dane z Croatia: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class HRSupervisor(CountrySupervisor):
    """Supervisor agentow dla Croatia."""

    def __init__(self):
        super().__init__(country_code="HR", config_path=CONFIG_PATH)
        self.load_config()
