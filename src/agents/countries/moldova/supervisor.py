"""Country Supervisor dla Moldova (MD).

Zarzadza agentami zbierajacymi dane z Moldova: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class MDSupervisor(CountrySupervisor):
    """Supervisor agentow dla Moldova."""

    def __init__(self):
        super().__init__(country_code="MD", config_path=CONFIG_PATH)
        self.load_config()
