from .huawei import HuaweiInverter
from .solarassistant import SolarAssistantInverter
from .solarman import SolarmanInverter
from .sofar import SofarInverter
from .esphome import EspHomeInverter

# from .deye_synsynk import SynsynkInverter
# from .growatt import GrowattInverter

INVERTER_INTEGRATIONS = {
    # "Synsynk": SynsynkInverter,
    "SolarAssistant": SolarAssistantInverter,
    "Solarman": SolarmanInverter,
    "Sofar": SofarInverter,
    "Huawei": HuaweiInverter,
    "EspHome": EspHomeInverter,
}


def get_inverter_class(model_name):
    try:
        return INVERTER_INTEGRATIONS[model_name]
    except KeyError:
        raise ValueError(f"Unsupported inverter model: {model_name}")
