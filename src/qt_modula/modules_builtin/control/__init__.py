"""Control built-in modules."""

from qt_modula.modules_builtin.control.interval_pulse import IntervalPulseModule
from qt_modula.modules_builtin.control.log_notes import LogNotesModule
from qt_modula.modules_builtin.control.number_input import NumberInputModule
from qt_modula.modules_builtin.control.options import OptionsModule
from qt_modula.modules_builtin.control.text_input import TextInputModule
from qt_modula.modules_builtin.control.trigger_button import TriggerButtonModule
from qt_modula.modules_builtin.control.trigger_debounce import TriggerDebounceModule
from qt_modula.modules_builtin.control.trigger_delay import TriggerDelayModule
from qt_modula.modules_builtin.control.trigger_mapper import TriggerMapperModule
from qt_modula.modules_builtin.control.trigger_rate_limit import TriggerRateLimitModule
from qt_modula.modules_builtin.control.value_view import ValueViewModule

__all__ = [
    "IntervalPulseModule",
    "LogNotesModule",
    "NumberInputModule",
    "OptionsModule",
    "TextInputModule",
    "TriggerButtonModule",
    "TriggerDebounceModule",
    "TriggerDelayModule",
    "TriggerMapperModule",
    "TriggerRateLimitModule",
    "ValueViewModule",
]
