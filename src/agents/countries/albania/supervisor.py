"""Country Supervisor dla Albania (AL).

Zarzadza agentami zbierajacymi dane z Albania: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class ALSupervisor(CountrySupervisor):
    """Supervisor agentow dla Albania."""

    def __init__(self):
        super().__init__(country_code="AL", config_path=CONFIG_PATH)
        self.load_config()
