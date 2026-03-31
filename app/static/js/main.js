/**
 * DigiBioFi — Main JavaScript
 *
 * Lightweight vanilla JS. No framework dependency.
 */

// ── Mobile menu toggle ────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("mobile-menu-btn");
  const menu = document.getElementById("mobile-menu");

  if (btn && menu) {
    btn.addEventListener("click", () => {
      menu.classList.toggle("hidden");
    });

    // Close mobile menu when clicking a link inside it
    menu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        menu.classList.add("hidden");
      });
    });
  }

  // ── Flash messages: auto-dismiss after 4 seconds ───────────────────────────
  document.querySelectorAll("[data-auto-dismiss]").forEach((el) => {
    setTimeout(() => {
      el.style.transition = "opacity 0.4s";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 400);
    }, 4000);
  });

  // ── File input preview ─────────────────────────────────────────────────────
  const imageInputs = document.querySelectorAll('input[type="file"][data-preview]');
  imageInputs.forEach((input) => {
    input.addEventListener("change", () => {
      const previewId = input.dataset.preview;
      const preview = document.getElementById(previewId);
      if (!preview || !input.files[0]) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        preview.src = e.target.result;
        preview.style.display = "block";
      };
      reader.readAsDataURL(input.files[0]);
    });
  });
});
