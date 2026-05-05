"""Country Supervisor dla San Marino (SM).

Zarzadza agentami zbierajacymi dane z San Marino: policja, media, fora,
telegram, reddit, alerty drogowe, rejestry finansowe.
Laduje konfiguracje z config.yaml, monitoruje zdrowie agentow
i raportuje do Master Supervisora.
"""

from pathlib import Path

from src.agents.base_supervisor import CountrySupervisor

CONFIG_PATH = Path(__file__).parent / "config.yaml"


class SMSupervisor(CountrySupervisor):
    """Supervisor agentow dla San Marino."""

    def __init__(self):
        super().__init__(country_code="SM", config_path=CONFIG_PATH)
        self.load_config()
