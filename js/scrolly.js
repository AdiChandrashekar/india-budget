// Scrollytelling: a sticky graphic, and steps that scroll past it.
//
// A step becomes active when it crosses the middle band of the viewport, and
// the graphic is told which step is active. That is the whole mechanism. The
// graphic owns its own transitions and must be able to jump to any step from
// any other, because readers scroll backwards and skip.

export function scrolly(root, onStep) {
  if (!root) return null;
  const steps = [...root.querySelectorAll(".step")];
  if (!steps.length) return null;

  let current = -1;
  const activate = (i) => {
    if (i === current) return;
    current = i;
    steps.forEach((s, j) => s.classList.toggle("is-active", j === i));
    onStep(i, steps[i].dataset);
  };

  // Without IntersectionObserver every step's content is still on the page;
  // show the graphic in its final, most complete state.
  if (!("IntersectionObserver" in window)) {
    activate(steps.length - 1);
    return null;
  }

  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) activate(steps.indexOf(e.target));
    }
  }, { rootMargin: "-45% 0px -45% 0px", threshold: 0 });

  steps.forEach((s) => io.observe(s));
  activate(0);
  return { destroy: () => io.disconnect(), get step() { return current; } };
}

// A thin bar along the top edge showing how far through the piece the reader
// is. Long-form scrolling pieces lose people without one.
export function progressBar(el) {
  if (!el) return;
  let ticking = false;
  const update = () => {
    const doc = document.documentElement;
    const max = doc.scrollHeight - doc.clientHeight;
    const t = max > 0 ? Math.min(1, Math.max(0, doc.scrollTop / max)) : 0;
    el.style.transform = "scaleX(" + t + ")";
    ticking = false;
  };
  window.addEventListener("scroll", () => {
    if (!ticking) { ticking = true; requestAnimationFrame(update); }
  }, { passive: true });
  update();
}
