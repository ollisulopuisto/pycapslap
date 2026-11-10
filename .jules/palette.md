## 2026-11-03 - Accessible file inputs in label wrapper buttons
**Learning:** Adding the HTML `hidden` attribute to `<input type="file">` inside a stylized `<label>` completely removes the input from the browser's accessibility tree and keyboard tab order (`display: none !important`), making the file picker unreachable for keyboard-only users. Using accessible off-screen / clipped styles (`position: absolute; width: 1px; height: 1px; clip: rect(0, 0, 0, 0);`) retains full keyboard focusability without changing the visual button appearance, and `:has(:focus-visible)` on the wrapper label surfaces the focus ring when navigated via keyboard.
**Action:** When styling custom file upload controls using `<label>` wrappers, never use the `hidden` attribute or `display: none` on the file input; use visually-hidden clipping and bubble `:focus-visible` up to the label with `.picker:has(:focus-visible)`.

## 2026-11-03 - Global :focus-visible across sister frontend subprojects
**Learning:** In multi-frontend repositories sharing design tokens (e.g., `--accent: #4f46e5` / `#6366f1`), omitting `:focus-visible` rings in secondary frontends leaves interactive controls (buttons, inputs, tabs, action links) relying on default UA focus indicators, which fail contrast checks or disappear entirely against dark themes (`#111113`).
**Action:** Ensure all CSS stylesheets across client-facing web surfaces (`review`, `portal`) define standard `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` to maintain keyboard accessibility parity.

## 2026-11-06 - Global spacebar media shortcuts breaking standard button activation
**Learning:** Registering a document-level `keydown` listener for `Space` that only checks `['INPUT', 'TEXTAREA'].includes(activeElement.tagName)` breaks native keyboard interaction for `<button>` and `<a>` elements (`e.preventDefault()` halts browser-native button activation on Space).
**Action:** When implementing global media play/pause hotkeys on `Space`, exempt all interactive elements (`BUTTON`, `A`, `SELECT`, `INPUT`, `TEXTAREA`) so keyboard users can navigate to and activate buttons with Space as expected by accessibility standards.

## 2026-11-10 - Generic class queries overwriting sibling form controls
**Learning:** Querying for generic utility classes like `.muted` within a form (`document.querySelector('form .muted')`) to inject status messages will collide with preceding form elements styled with the same utility class (such as `<label class="muted">` containing `<select>`), destroying essential form controls and confusing screen readers.
**Action:** Always give status elements a distinct semantic identifier (e.g., `.status`), mark them with `role="status"` and `aria-live="polite"`, and disable the submit button during in-flight network requests to prevent duplicate submissions.
