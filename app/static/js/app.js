/* Utilitários Alpine.js + HTMX para Bem Me Quero · Estoque */
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) {
    const busca = document.getElementById("bmq-global-search");
    if (busca) {
      e.preventDefault();
      busca.focus();
      busca.select();
    }
  }
});

window.bmqToast = function (mensagem, tipo = "sucesso") {
  window.dispatchEvent(new CustomEvent("bmq-toast", { detail: { mensagem, tipo } }));
};

document.body?.addEventListener("htmx:responseError", (e) => {
  window.bmqToast("Não foi possível concluir a operação.", "erro");
});

