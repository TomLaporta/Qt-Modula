# Module Catalog

This catalog is the index for the built-in module reference set.

- built-in modules in the current registry: `43`
- module doc pages in this folder: `43`
- implementation source: `src/qt_modula/modules_builtin/`

Detailed contracts, runtime notes, and examples live in each module page. This catalog stays intentionally concise so it does not drift from those per-module references.

## Control

- `interval_pulse` - `Interval Pulse` - `source, scheduler` - [INTERVAL_PULSE.md](./INTERVAL_PULSE.md)
- `log_notes` - `Log Notes` - `sink` - [LOG_NOTES.md](./LOG_NOTES.md)
- `number_input` - `Number Input` - `source, scheduler` - [NUMBER_INPUT.md](./NUMBER_INPUT.md)
- `options` - `Options` - `source, scheduler` - [OPTIONS.md](./OPTIONS.md)
- `text_input` - `Text Input` - `source, scheduler` - [TEXT_INPUT.md](./TEXT_INPUT.md)
- `trigger_button` - `Trigger Button` - `source, scheduler` - [TRIGGER_BUTTON.md](./TRIGGER_BUTTON.md)
- `trigger_debounce` - `Trigger Debounce` - `transform, scheduler` - [TRIGGER_DEBOUNCE.md](./TRIGGER_DEBOUNCE.md)
- `trigger_delay` - `Trigger Delay` - `transform, scheduler` - [TRIGGER_DELAY.md](./TRIGGER_DELAY.md)
- `trigger_mapper` - `Trigger Mapper` - `transform, scheduler` - [TRIGGER_MAPPER.md](./TRIGGER_MAPPER.md)
- `trigger_rate_limit` - `Trigger Rate Limit` - `gate, transform` - [TRIGGER_RATE_LIMIT.md](./TRIGGER_RATE_LIMIT.md)
- `value_view` - `Value View` - `sink` - [VALUE_VIEW.md](./VALUE_VIEW.md)

## Providers

- `fx_quote` - `FX Quote` - `provider, source` - [FX_QUOTE.md](./FX_QUOTE.md)
- `http_request` - `HTTP Request` - `provider, source` - [HTTP_REQUEST.md](./HTTP_REQUEST.md)
- `market_fetcher` - `Market Fetcher` - `provider, source` - [MARKET_FETCHER.md](./MARKET_FETCHER.md)

## Import

- `text_import` - `Text Import` - `source` - [TEXT_IMPORT.md](./TEXT_IMPORT.md)
- `json_import` - `JSON Import` - `source` - [JSON_IMPORT.md](./JSON_IMPORT.md)
- `table_import` - `Table Import` - `source` - [TABLE_IMPORT.md](./TABLE_IMPORT.md)

## Transform

- `datetime_convert` - `Datetime Convert` - `transform` - [DATETIME_CONVERT.md](./DATETIME_CONVERT.md)
- `json_project` - `JSON Project` - `transform` - [JSON_PROJECT.md](./JSON_PROJECT.md)
- `json_transform` - `JSON Transform` - `transform` - [JSON_TRANSFORM.md](./JSON_TRANSFORM.md)
- `table_transform` - `Table Transform` - `transform` - [TABLE_TRANSFORM.md](./TABLE_TRANSFORM.md)
- `template_formatter` - `Template Formatter` - `transform` - [TEMPLATE_FORMATTER.md](./TEMPLATE_FORMATTER.md)
- `value_scanner` - `Value Scanner` - `transform` - [VALUE_SCANNER.md](./VALUE_SCANNER.md)
- `value_wrapper` - `Value Wrapper` - `transform` - [VALUE_WRAPPER.md](./VALUE_WRAPPER.md)

## Logic

- `circuit_breaker` - `Circuit Breaker` - `gate, transform` - [CIRCUIT_BREAKER.md](./CIRCUIT_BREAKER.md)
- `condition_gate` - `Condition Gate` - `gate, transform` - [CONDITION_GATE.md](./CONDITION_GATE.md)
- `logic_combinator` - `Logic Combinator` - `gate, transform` - [LOGIC_COMBINATOR.md](./LOGIC_COMBINATOR.md)
- `retry_controller` - `Retry Controller` - `gate, transform` - [RETRY_CONTROLLER.md](./RETRY_CONTROLLER.md)
- `trigger_join` - `Trigger Join` - `gate, transform` - [TRIGGER_JOIN.md](./TRIGGER_JOIN.md)
- `trigger_join_n` - `Trigger Join N` - `gate, transform` - [TRIGGER_JOIN_N.md](./TRIGGER_JOIN_N.md)
- `value_change_gate` - `Value Change Gate` - `gate, transform` - [VALUE_CHANGE_GATE.md](./VALUE_CHANGE_GATE.md)
- `value_latch` - `Value Latch` - `gate, transform` - [VALUE_LATCH.md](./VALUE_LATCH.md)
- `value_router` - `Value Router` - `gate, transform` - [VALUE_ROUTER.md](./VALUE_ROUTER.md)
- `value_selector` - `Value Selector` - `gate, transform` - [VALUE_SELECTOR.md](./VALUE_SELECTOR.md)

## Math

- `arithmetic` - `Arithmetic` - `transform` - [ARITHMETIC.md](./ARITHMETIC.md)
- `formula_calculator` - `Formula Calculator` - `transform` - [FORMULA_CALCULATOR.md](./FORMULA_CALCULATOR.md)

## Research

- `parameter_sweep` - `Parameter Sweep` - `transform, source` - [PARAMETER_SWEEP.md](./PARAMETER_SWEEP.md)
- `table_buffer` - `Table Buffer` - `transform` - [TABLE_BUFFER.md](./TABLE_BUFFER.md)

## Analytics

- `line_plotter` - `Line Plotter` - `sink, transform` - [LINE_PLOTTER.md](./LINE_PLOTTER.md)
- `rolling_stats` - `Rolling Stats` - `transform, sink` - [ROLLING_STATS.md](./ROLLING_STATS.md)
- `table_metrics` - `Table Metrics` - `transform` - [TABLE_METRICS.md](./TABLE_METRICS.md)

## Export

- `table_export` - `Table Export` - `sink` - [TABLE_EXPORT.md](./TABLE_EXPORT.md)
- `text_export` - `Text Export` - `sink` - [TEXT_EXPORT.md](./TEXT_EXPORT.md)
