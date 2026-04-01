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

  // ── Flash messages: auto-dismiss ───────────────────────────────────────────
  document.querySelectorAll(".flash-message").forEach((el) => {
    setTimeout(() => {
      el.style.transform = "translateX(100%)";
      el.style.opacity = "0";
      el.style.transition = "transform 0.4s ease-in, opacity 0.4s ease-in";
      setTimeout(() => el.remove(), 400);
    }, 5000);
  });

  // ── Form loading states ────────────────────────────────────────────────────
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (e) => {
      // Check if it's a file upload (might take time)
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) {
        // Prevent multiple clicks
        if (submitBtn.classList.contains("btn-loading")) {
          e.preventDefault();
          return;
        }
        
        // Only show loading if form is valid (client-side)
        if (form.checkValidity && !form.checkValidity()) return;

        // Change text if provided via data attribute
        if (submitBtn.dataset.loadingText) {
          submitBtn.dataset.originalText = submitBtn.innerHTML;
          submitBtn.innerHTML = submitBtn.dataset.loadingText;
        }
        
        submitBtn.classList.add("btn-loading");
      }
    });
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
