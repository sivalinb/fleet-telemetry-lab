# HTML demo keynote

The keynote is a 12-slide engineering pitch for Telemetry Reliability Lab. It explains the problem, demonstrates measured crash recovery, and proposes a small team pilot. It includes presenter notes and source links on the slides that use recorded results.

## Open and present

With the lab API running, open **http://127.0.0.1:8001/docs-guide/keynote.html**.

You can also download `docs/keynote.html` and open it directly in a modern browser. The file contains its styles, charts, and downloadable replay evidence. The presentation and recorded demo need no server or network connection. External source links and the live Gradio demo still need their destinations to be available. GitHub's file viewer shows the HTML source, so download the file to present it.

- **Next / Back:** move between slides. **Slides:** jump to a section.
- **Notes:** open the talk track for the current slide. Close it before continuing.
- **Keyboard:** use Tab to focus a link or control, then Enter. Focused radio controls also support the browser's arrow-key behavior. Browser Back and Forward follow slide history.
- **Full screen:** use your browser's full-screen control. The deck uses native HTML navigation, without a custom fullscreen script.
- **Print:** the print stylesheet includes all 12 slides, hides presentation controls, and shows the persistent queue's final recorded result on the demo slide. Choose landscape if your browser overrides the declared page size. Print-preview behavior can vary by browser.

## A five-minute talk

| Time | Slides | Focus |
| --- | --- | --- |
| 0:00–0:45 | 1–2 | A telemetry receiver accepting a request does not establish end-to-end delivery |
| 0:45–1:30 | 3–4 | Repeatable investigation and the two execution paths |
| 1:30–3:00 | 5 | Step through persistence, then repeat with the in-memory queue |
| 3:00–3:45 | 6–9 | Interpret loss correctly and show the existing verification |
| 3:45–5:00 | 10–12 | A small pilot, scaling requirements, and an invitation to inspect the source |

For a shorter pitch, use slides 1, 2, 5, 6, and 12. The **Slides** menu lets you jump without editing the deck.

## Recorded demo and live demo

Slide 5 is an **interactive replay of checked-in observations**, not a simulator or a new live run. Choose a storage type, then use **Backlog**, **Restart**, and **Verify delivery**. The numbers and queue curves come from `evidence/reliability/durable-crash.json` and `volatile-crash.json`. Each original run sent 12 traces and 12 logs. Final totals count only those originals and exclude the fresh recovery canary.

The live-demo link opens Gradio on port 7860. With the stack ready, run the persistent crash with 12 inputs, then the in-memory crash. Open History, compare the rows, and download either report. A passing loss experiment confirms its stated hypothesis. It does not mean every attempted signal arrived.

## Edit and rebuild

```sh
python scripts/build_keynote.py
# Set a different live-demo address when you have a running deployment:
python scripts/build_keynote.py --demo-url https://your-demo.example
```

Edit the slide copy and notes in `scripts/build_keynote.py`; edit the layout in `docs/keynote.css`. The generator embeds the CSS and evidence into `docs/keynote.html`. It rejects nonpassing source runs instead of turning them into a verified result.

All presentation generation is Python. The HTML uses anchors, details elements, and radio inputs for navigation and replay. There is no custom JavaScript, CDN, tracking, or external font dependency.

The verification slide cites the tested lab at commit `586fd11`, and the related CI run. Keep that provenance aligned if you replace the underlying evidence. The scalability numbers are explicitly illustrative. The deck makes no production deployment, GPU benchmark, or financial-return claim.
