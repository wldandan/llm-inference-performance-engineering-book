from pathlib import Path
import subprocess
import unittest


WORKSHOP_DIR = Path(__file__).resolve().parent


class RunExperimentTest(unittest.TestCase):
    def test_has_one_command_experiment_entrypoint(self):
        self.assertTrue((WORKSHOP_DIR / "run_experiment.sh").is_file())

    def test_dry_run_shows_baseline_optimized_and_comparison_steps(self):
        result = subprocess.run(
            ["bash", "run_experiment.sh", "--dry-run"],
            cwd=WORKSHOP_DIR,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--no-enable-prefix-caching", result.stdout)
        self.assertIn("--enable-prefix-caching", result.stdout)
        self.assertIn("bench_baseline.sh", result.stdout)
        self.assertIn("bench_optimized.sh", result.stdout)
        self.assertIn("output_throughput_tokens_per_second", result.stdout)

    def test_shared_wrapper_can_record_a_known_engine_batch_size(self):
        wrapper = (WORKSHOP_DIR.parent / "common" / "bench.sh").read_text(encoding="utf-8")

        self.assertIn("BATCH_SIZE", wrapper)
        self.assertIn("--batch-size", wrapper)

    def test_shared_server_uses_the_public_vllm_cli(self):
        launcher = (WORKSHOP_DIR.parent / "common" / "serve.sh").read_text(encoding="utf-8")

        self.assertIn('exec vllm serve "$MODEL"', launcher)

    def test_variant_launchers_exec_the_server_so_cleanup_reaches_vllm(self):
        for name in ("serve_baseline.sh", "serve_optimized.sh"):
            launcher = (WORKSHOP_DIR / name).read_text(encoding="utf-8")
            self.assertIn("exec bash ../common/serve.sh", launcher, name)

    def test_entrypoint_refuses_to_benchmark_an_unrelated_existing_server(self):
        entrypoint = (WORKSHOP_DIR / "run_experiment.sh").read_text(encoding="utf-8")

        self.assertIn("A server is already responding at", entrypoint)


if __name__ == "__main__":
    unittest.main()
