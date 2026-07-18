/**
 * <vdsl-player> — drop-in Web Component to embed an A2TL-Video in any web page.
 *
 * The A2TL-Video player is a self-contained HTML document (produced by
 * `vdsl play` or `renderToHTML()`). This component hosts that document inside
 * a responsive, style-isolated <iframe>, so it can't leak CSS in or out of
 * your page.
 *
 * Part of A2TL-Video (Agent to Transformation Language for Video).
 * The <vdsl-player> tag name is kept for backwards compatibility.
 *
 * Usage:
 *   <script src="vdsl-player.js"></script>
 *
 *   <!-- by URL to a generated player HTML file -->
 *   <vdsl-player src="communication.html"></vdsl-player>
 *
 *   <!-- or inline the full player HTML -->
 *   <vdsl-player srcdoc="<!DOCTYPE html>..."></vdsl-player>
 *
 *   <!-- or set it from JS (e.g. HTML returned by your backend) -->
 *   document.querySelector('vdsl-player').html = generatedHtml;
 *
 * Attributes:
 *   src        URL of a generated player .html
 *   srcdoc     full player HTML as a string
 *   ratio      aspect ratio, default "16/9"
 *   autoplay   if present, presses play once the player is ready
 *   maxwidth   CSS max-width for the frame, default "100%"
 */
(function () {
  if (customElements.get("vdsl-player")) return;

  class VdslPlayer extends HTMLElement {
    static get observedAttributes() { return ["src", "srcdoc", "ratio", "maxwidth"]; }

    constructor() {
      super();
      this._root = this.attachShadow({ mode: "open" });
      this._html = null;
    }

    connectedCallback() { this._render(); }
    attributeChangedCallback() { this._render(); }

    /** Set the full player HTML from JavaScript (overrides src/srcdoc). */
    set html(v) { this._html = v; this._render(); }
    get html() { return this._html; }

    /** Access the player control API (seek/play/pause) inside the iframe, if ready. */
    get player() {
      const f = this._root.querySelector("iframe");
      try { return f && f.contentWindow ? f.contentWindow.vdslPlayer : null; } catch (e) { return null; }
    }

    _render() {
      const ratio = this.getAttribute("ratio") || "16/9";
      const maxWidth = this.getAttribute("maxwidth") || "100%";
      const src = this.getAttribute("src");
      const srcdoc = this._html || this.getAttribute("srcdoc");
      const autoplay = this.hasAttribute("autoplay");

      this._root.innerHTML =
        '<style>' +
        ':host{display:block;width:100%}' +
        '.frame{position:relative;width:100%;max-width:' + maxWidth + ';aspect-ratio:' + ratio + ';margin:0 auto;' +
        'border-radius:12px;overflow:hidden;background:#111}' +
        'iframe{position:absolute;inset:0;width:100%;height:100%;border:0;display:block}' +
        '</style>' +
        '<div class="frame"><iframe' +
        (src && !srcdoc ? ' src="' + src.replace(/"/g, "&quot;") + '"' : "") +
        ' allow="autoplay" scrolling="no"></iframe></div>';

      const iframe = this._root.querySelector("iframe");
      if (srcdoc) iframe.srcdoc = srcdoc;

      if (autoplay) {
        iframe.addEventListener("load", () => {
          const tryPlay = (n) => {
            const p = this.player;
            if (p && p.play) p.play();
            else if (n > 0) setTimeout(() => tryPlay(n - 1), 100);
          };
          tryPlay(20);
        });
      }
    }
  }

  customElements.define("vdsl-player", VdslPlayer);
})();
