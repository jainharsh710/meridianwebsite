"""Entry point used by GitHub Actions.

    python -m automation.run prepare        # learn, plan, research, write, check, build (no push)
    python -m automation.run post-publish   # after the push: confirm live, IndexNow, sitemap, publish email
    python -m automation.run daily-index    # check whether recent posts are indexed
    python -m automation.run seed           # create the data files from the current site (safe to rerun)
"""
import json
import sys
import traceback

from automation.engine import config, integrations as ext, llm, pipeline, store


def _run():
    rid = config.now_ist().strftime("%Y-%m-%d")
    return store.Run(rid)


def main(cmd):
    if cmd == "seed":
        pipeline.ensure_seed()
        print("seeded")
        return 0
    if cmd == "daily-index":
        pipeline.daily_index()
        return 0
    if cmd == "prepare":
        run = _run()
        try:
            state = pipeline.prepare(run)
        except llm.BudgetExceeded as e:
            state = pipeline.hold(run, str(e), None)
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc()
            run.write("error.txt", tb)
            run.set_state(status="FAILED", publish_ready=False, error=str(e), cost=llm.summary())
            ext.send_email("FAILED: Meridian content engine",
                           f"<p style='font-family:Arial'>This week's run stopped with an error before publishing:</p>"
                           f"<pre>{str(e)[:1500]}</pre><p style='font-family:Arial'>Nothing was published. "
                           "Next Monday's run starts fresh.</p>")
            print(tb, file=sys.stderr)
            return 1
        run.write("log.txt", "\n".join(ext.LOG))
        print(json.dumps({k: state.get(k) for k in ("status", "slug", "title", "cost")}, indent=1))
        # Tell the workflow whether to push.
        gh = __import__("os").environ.get("GITHUB_OUTPUT")
        if gh:
            with open(gh, "a") as fh:
                fh.write(f"publish_ready={'true' if state.get('publish_ready') else 'false'}\n")
                fh.write(f"run_dir={run.dir.relative_to(config.ROOT)}\n")
        return 0
    if cmd == "post-publish":
        rd = store.latest_run_dir()
        run = store.Run(rd.name)
        state = pipeline.post_publish(run)
        print(json.dumps({k: state.get(k) for k in ("status", "url", "indexnow", "sitemap_submitted")}, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
