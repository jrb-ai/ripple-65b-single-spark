# Ripple-65B on one DGX Spark

Serve Ricursive AI's [Ripple-65B-Preview](https://huggingface.co/ricursiveAI/Ripple-65B-Preview-NVFP4) (NVFP4) with
its [DFlash2 drafter](https://huggingface.co/ricursiveAI/Ripple-65B-Preview-DFlash2) on one NVIDIA DGX Spark, with
TensorFold's native CUDA engine. The model, the drafter and eight streams fit in the Spark's 128 GB of unified memory.

TensorFold reads both checkpoints as published. Only the MLP weights are 4-bit (NVFP4). Attention, the embeddings and
the output head run in BF16, with BF16 activations. Every drafted reply equals the plain reply, token for token.

Status: tested on 9 November 2026. TensorFold's CUDA support for Ripple is in two open pull requests:
[#2302](https://github.com/ashhart/TensorFold/pull/2302) (the model) and
[#2475](https://github.com/ashhart/TensorFold/pull/2475) (the drafter). They are not merged, and TensorFold's
maintainers have not yet decided whether to take the Ripple family
([#2171](https://github.com/ashhart/TensorFold/issues/2171)). The tested build is the branch
[`ricursive-cuda-speed`](https://github.com/jrb-ai/tensorfold-ripple/tree/ricursive-cuda-speed) of
jrb-ai/tensorfold-ripple, at `2c35738cd`. It is #2475 plus two changes: a fix to how the drafter prices rounds that
several streams share, and faster prompt kernels.

## Results

One DGX Spark, 9 November 2026, build `2c35738cd`, all runs in one session. Plain is #2302's code without the drafter.
Every stream sends the same prompt: one for code (a raw text completion) and one for prose (a chat reply, thinking
off). Each reply runs to exactly 256 tokens. Each sampled stream (T=1.0) has its own seed. Median of 3 reps.

Total tok/s, plain → drafted:

| Streams | Code, greedy | Code, T=1.0 | Prose, greedy | Prose, T=1.0 |
|---:|---:|---:|---:|---:|
| 1 | 5.2 → 24.1 | 4.0 → 12.6 | 4.4 → 10.4 | 4.0 → 14.5 |
| 2 | 10.3 → 55.6 | 8.0 → 19.4 | 8.6 → 19.4 | 8.0 → 16.0 |
| 4 | 20.0 → 85.0 | 15.7 → 34.4 | 16.9 → 35.9 | 15.7 → 29.7 |
| 8 | 37.3 → 124.4 | 30.3 → 60.4 | 32.4 → 61.5 | 30.3 → 52.1 |

- One stream on greedy code runs at 24.1 tok/s, 4.6x plain. Eight streams run at 124.4 tok/s in total, 15.5 tok/s for
  each stream, 3.3x plain.
- At 8 streams on greedy code, each stream drafts about 8 tokens a round and the model keeps about 6.
- The shared-round fix matters when streams share a round. Without it (#2475 at `3065161da`), 8 streams on greedy code
  gave 49.1 tok/s in total, and each stream drafted about 1 token a round. One stream is the same with or without it.
- All 180 drafted replies equal the plain replies (90 greedy, 90 sampled).
- The speed-up is only as good as the drafter. It gains most on greedy code, where the next tokens are the most
  predictable.
- Every stream sends the same prompt, so the 8 greedy streams write the same reply. Expect lower totals with a
  different prompt per stream.

Tested on DGX OS (Ubuntu 24.04.5, kernel 7.0.0-1019-nvidia), NVIDIA driver 580.178.04, Zig 0.17 and CUDA 13 (nvcc 13.3).

## Steps

1. Download the checkpoints at the tested revisions (about 62 GiB: 54 GiB for the model, 7.6 GiB for the drafter).
   With `-q`, each command prints only the local folder.

   ```bash
   RIPPLE=$(hf download ricursiveAI/Ripple-65B-Preview-NVFP4 --revision 99eea4477a001a41b86914e41feb4b2ed86105e5 -q)
   DRAFT=$(hf download ricursiveAI/Ripple-65B-Preview-DFlash2 --revision 35609b3be3dd08a822b3ba1257c1ea5dd6f87632 -q)
   ```

2. Build the server:

   ```bash
   git clone https://github.com/jrb-ai/tensorfold-ripple && cd tensorfold-ripple && git checkout 2c35738cd
   zig build native -Dnvcc=/usr/local/cuda/bin/nvcc -Dsm=121
   ```

3. Stop every other GPU workload. Set `RECIPE` to this repository's folder, drop the checkpoints' pages, and check
   that MemFree is near 100 GiB:

   ```bash
   python3 "$RECIPE/scripts/evict.py" "$RIPPLE" "$DRAFT"
   grep MemFree /proc/meminfo
   ```

4. Start the server and its memory guard:

   ```bash
   zig-out/native/bin/tensorfold-native serve "$RIPPLE" --name ripple --port 8888 --context 32768 --drafter "$DRAFT" &
   "$RECIPE/scripts/mem-guard.sh" $! &
   ```

5. Send a request:

   ```bash
   curl -s localhost:8888/v1/chat/completions -H 'Content-Type: application/json' \
     -d '{"model": "ripple", "max_tokens": 512,
          "messages": [{"role": "user", "content": "What is the capital of France?"}]}'
   ```

6. Stop the server with `kill` on its process. The memory guard stops when the server stops.

Not supported on CUDA yet: structured output (`response_format`) and forced tool calls. The server refuses them.
Tool calls with `tool_choice` `"auto"` work.

## Why these settings

- **Free memory before the load.** The GB10 driver needs free pages, not reclaimable page cache. Reading 62 GiB of
  checkpoint fills the page cache. `scripts/evict.py` drops those pages (`posix_fadvise`, no root needed).
- **The memory guard.** `scripts/mem-guard.sh` stops the server if MemAvailable falls below 6 GiB. On the Spark, an
  out-of-memory event can kill system services, not only the server. If the guard stops the server, lower `--context`
  before you try again. Do not lower `vm.min_free_kbytes` to make room.
- **`--context 32768`.** At this context the server admits eight streams of 3.01 GiB each and an 11.2 GiB prompt cache.
  The drafter keeps 10.09 GiB for its weights, scratch and the eight streams' rings.

## Licences and credits

- Ripple-65B-Preview NVFP4 and Ripple-65B-Preview-DFlash2: Ricursive AI, Apache-2.0.
- TensorFold: Apache-2.0. Its Ripple CUDA support and DFlash2 drafter code are in the pull requests above.
