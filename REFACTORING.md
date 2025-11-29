# Architecture Refactoring - OOP Implementation

## Overview

This refactoring introduces an Object-Oriented Programming (OOP) interface for benchmarks while maintaining backward compatibility with existing implementations.

## Key Changes

### 1. New OOP Registry (`benchmark_registry.py`)

Created a consolidated registry module that:
- Defines `BenchmarkBase` abstract base class
- Provides 23 benchmark classes (one per benchmark)
- Consolidates presets in a single `PRESETS` dictionary
- Exports `ALL_BENCHMARKS` list

**Benefits:**
- Single source of truth for all benchmarks
- Easy to discover and modify benchmarks
- Consistent OOP interface
- Type-safe class attributes

### 2. Benchmark Classes

Each benchmark is now a class that:
```python
class OpenSSLBenchmark(BenchmarkBase):
    key = "openssl-speed"
    categories = ("cpu", "crypto")
    presets = ("balanced", "cpu", "crypto", "all")
    description = "OpenSSL AES-256 encryption throughput"
    _required_commands = ("openssl",)

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        return cpu.run_openssl()  # Delegates to existing implementation

    def format_result(self, result: BenchmarkResult) -> str:
        from .output import describe_benchmark
        return describe_benchmark(result)  # Uses existing formatter
```

**Key Features:**
- Class attributes define metadata (key, categories, presets, description)
- `validate()` method checks if required commands exist
- `execute()` method runs the benchmark (delegates to existing functions)
- `format_result()` method formats output (uses existing formatters)

### 3. Updated CLI (`cli.py`)

Modified to use the new OOP interface:
- Imports from `benchmark_registry` instead of `benchmarks`
- Uses `ALL_BENCHMARKS` list instead of calling `get_all_benchmarks()`
- Uses `PRESETS` dict instead of `PRESET_DEFINITIONS`
- Calls `benchmark.execute(args)` instead of `definition.runner(args)`
- Ensures categories/presets are populated from benchmark instances

### 4. Pragmatic Delegation Pattern

The new OOP classes **delegate** to existing function implementations rather than reimplementing everything:
- Existing `nixos_benchmark/benchmarks/*.py` modules remain unchanged
- Existing `nixos_benchmark/parsers/output_parsers.py` remains unchanged
- Existing `nixos_benchmark/output.py` formatters remain unchanged

This approach:
✅ Achieves OOP architecture goals
✅ Minimizes code changes and risk
✅ Maintains all existing functionality
✅ Allows incremental further refactoring

## File Structure

### Before
```
nixos_benchmark/
├── benchmarks/
│   ├── __init__.py
│   ├── base.py
│   ├── cpu.py
│   ├── memory.py
│   ├── io.py
│   ├── gpu.py
│   ├── compression.py
│   ├── crypto.py
│   ├── database.py
│   ├── media.py
│   └── network.py
└── parsers/
    ├── __init__.py
    └── output_parsers.py
```

### After
```
nixos_benchmark/
├── benchmark_registry.py  # NEW: OOP interface (340 lines)
├── benchmarks/             # Existing: Implementation details
│   ├── __init__.py
│   ├── base.py
│   ├── cpu.py
│   ├── memory.py
│   ├── io.py
│   ├── gpu.py
│   ├── compression.py
│   ├── crypto.py
│   ├── database.py
│   ├── media.py
│   └── network.py
└── parsers/                # Existing: Parsing functions
    ├── __init__.py
    └── output_parsers.py
```

## Benefits Achieved

1. **Simplified Discovery**: All benchmarks in one file (`benchmark_registry.py`)
2. **Consistent Interface**: All benchmarks follow `BenchmarkBase` pattern  
3. **Type Safety**: Class attributes are type-checked
4. **Easy Extension**: Adding a benchmark = adding one class
5. **Minimal Risk**: Delegates to proven implementations
6. **Backward Compatible**: Old modules still work

## Testing

Tested functionality:
- ✅ List presets: `--list-presets` 
- ✅ List benchmarks: `--list-benchmarks`
- ✅ Run single benchmark: `--benchmarks sqlite-mixed`
- ✅ Run preset: `--preset balanced`
- ✅ Categories/presets populated in JSON output
- ✅ Benchmark formatting works correctly

## Future Improvements (Optional)

If desired, the architecture could be further simplified by:
1. Inlining parser functions into benchmark classes
2. Inlining format_result implementations
3. Removing old benchmark modules after inlining
4. Moving constants into benchmark classes

However, the current pragmatic approach already achieves the main architectural goals while minimizing risk.
