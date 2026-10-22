import importlib.util
import math
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("gpu_model.py")


def load_gpu_model():
    if not MODULE_PATH.exists():
        raise AssertionError("code/advanced/gpu-architecture/gpu_model.py must exist")
    spec = importlib.util.spec_from_file_location("appendix_a_gpu_model", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GpuMentalModelTests(unittest.TestCase):
    def setUp(self):
        self.model = load_gpu_model()

    def test_model_weight_bytes_respects_parameter_precision(self):
        self.assertEqual(self.model.model_weight_bytes(500_000_000, 2), 1_000_000_000)
        self.assertEqual(self.model.model_weight_bytes(500_000_000, 1), 500_000_000)

    def test_kv_cache_bytes_counts_k_and_v_for_every_layer(self):
        actual = self.model.kv_cache_bytes(
            num_layers=24,
            num_kv_heads=2,
            head_dim=64,
            total_tokens=4096,
            bytes_per_element=2,
        )
        expected = 2 * 24 * 2 * 64 * 4096 * 2
        self.assertEqual(actual, expected)

    def test_gqa_reduces_kv_capacity_relative_to_mha(self):
        gqa = self.model.kv_cache_bytes(24, 2, 64, 4096, 2)
        mha = self.model.kv_cache_bytes(24, 14, 64, 4096, 2)
        self.assertEqual(mha / gqa, 7)

    def test_memory_budget_preserves_reserve_and_detects_overflow(self):
        budget = self.model.memory_budget(
            model_bytes=70,
            kv_bytes=20,
            workspace_bytes=5,
            gpu_memory_bytes=100,
            reserve_fraction=0.10,
        )
        self.assertFalse(budget["fits"])
        self.assertEqual(budget["usable_bytes"], 90)
        self.assertEqual(budget["required_bytes"], 95)
        self.assertEqual(budget["remaining_bytes"], -5)

    def test_compute_heavy_scenario_is_compute_limited(self):
        estimate = self.model.execution_lower_bounds(
            operations_flop=1e12,
            bytes_moved=1e8,
            peak_tflops=100,
            memory_bandwidth_gbps=2000,
            kernel_count=10,
            launch_us=5,
        )
        self.assertEqual(estimate["dominant_constraint"], "compute_throughput")
        self.assertTrue(math.isclose(estimate["compute_ms"], 10.0))

    def test_data_heavy_scenario_is_bandwidth_limited(self):
        estimate = self.model.execution_lower_bounds(
            operations_flop=1e9,
            bytes_moved=20e9,
            peak_tflops=100,
            memory_bandwidth_gbps=2000,
            kernel_count=10,
            launch_us=5,
        )
        self.assertEqual(estimate["dominant_constraint"], "memory_bandwidth")
        self.assertTrue(math.isclose(estimate["bandwidth_ms"], 10.0))

    def test_many_tiny_kernels_are_launch_sensitive(self):
        estimate = self.model.execution_lower_bounds(
            operations_flop=1e9,
            bytes_moved=1e6,
            peak_tflops=100,
            memory_bandwidth_gbps=2000,
            kernel_count=300,
            launch_us=5,
        )
        self.assertEqual(estimate["dominant_constraint"], "launch_overhead")
        self.assertTrue(math.isclose(estimate["launch_ms"], 1.5))

    def test_report_names_one_of_four_constraints_without_claiming_a_benchmark(self):
        report = self.model.build_report(
            model_parameters=500_000_000,
            bytes_per_parameter=2,
            num_layers=24,
            num_kv_heads=2,
            head_dim=64,
            active_tokens=4096,
            kv_bytes_per_element=2,
            workspace_bytes=200_000_000,
            gpu_memory_bytes=2_000_000_000,
            reserve_fraction=0.10,
            operations_flop=1e9,
            bytes_moved=20e9,
            peak_tflops=100,
            memory_bandwidth_gbps=2000,
            kernel_count=10,
            launch_us=5,
        )
        self.assertEqual(report["mode"], "synthetic_gpu_mental_model")
        self.assertEqual(report["dominant_constraint"], "memory_bandwidth")
        self.assertEqual(
            set(report["constraints"]),
            {"compute_throughput", "memory_capacity", "memory_bandwidth", "launch_overhead"},
        )
        self.assertIn("不是 Benchmark", report["note"])

    def test_non_positive_inputs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "model_parameters"):
            self.model.model_weight_bytes(0, 2)
        with self.assertRaisesRegex(ValueError, "peak_tflops"):
            self.model.execution_lower_bounds(1, 1, 0, 1, 1, 1)


if __name__ == "__main__":
    unittest.main()
