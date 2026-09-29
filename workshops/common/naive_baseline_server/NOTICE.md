# Attribution

The code in this directory (`llm/` and `main.py`) is adapted, largely unchanged, from the
companion repository of:

> *Hands-On LLM Serving and Optimization* — Chi Wang and Peiheng Hu, O'Reilly.
> Chapter 3, "Model-Serving System Design" — `ch03/single_model_llm_serving`.
> Repository: https://github.com/orca3/llm-model-inference

Used here as a **teaching baseline**: it's a from-scratch, plain-`transformers` (no vLLM)
implementation that happens to demonstrate both static batching (`/generate`, a single
blocking `model.generate()` call over a whole prompt list) and continuous/iteration-level
batching (`/generate_stream`, a background loop that tops up the active batch every step
as sequences finish — see `llm/workload_manager.py` `get_next_batch()` and
`llm/llm.py` `requests_processing_loop()`). That pairing is exactly the non-vLLM half of
Workshop 02's static-vs-continuous comparison and isn't something we wrote ourselves.

This course is used for internal/offline teaching, not republished as a product, so this
adaptation is kept close to the original with attribution rather than being a from-scratch
rewrite. If this course material is ever redistributed more broadly, revisit whether the
original authors/publisher should be asked directly rather than relying on this notice.
