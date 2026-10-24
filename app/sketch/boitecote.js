// Esquisse : la petite boîte flottante qui modifie une cote (valeur ou
// expression), près de son étiquette.

import { t } from "../i18n.js";
import { dimEditPayload } from "../dims.js";

export function installBoiteCote(sk) {
  const { renderer, call, refresh, mode, safe, editDim } = sk;

  // Petite boîte flottante près de la cote : la valeur mesurée est
  // sélectionnée, on tape la nouvelle (ou une expression), Entrée applique,
  // Échap garde la valeur mesurée. « … » ouvre le panneau complet (nom).

  let modifyBox = null;

  function closeModifyBox() {
    modifyBox?.remove();
    modifyBox = null;
  }

  function openModifyBox(dim, at) {
    closeModifyBox();
    const host = renderer.domElement.parentElement;
    const rect = host.getBoundingClientRect();
    const sketchDim = { ...dim, kind: "sketch" };
    const isSketchAngle = dim.type === "Angle";
    const shown = dim.expr
      || (isSketchAngle
        ? (dim.value * 180 / Math.PI).toFixed(2)
        : String(+Number(dim.value).toFixed(4)));
    const box = document.createElement("div");
    box.className = "dim-modify";
    box.dataset.ownKeys = "1"; // le panneau ne capte pas Entrée / Échap ici
    const input = document.createElement("input");
    input.type = "text";
    input.value = shown;
    input.title = t("Valeur ou expression — Entrée pour appliquer, Échap pour garder la valeur mesurée");
    const unitEl = document.createElement("span");
    unitEl.textContent = isSketchAngle ? "°" : "mm";
    const ok = document.createElement("button");
    ok.className = "ok";
    ok.textContent = "✓";
    ok.title = t("Appliquer (Entrée)");
    const cancel = document.createElement("button");
    cancel.className = "no";
    cancel.textContent = "✗";
    cancel.title = t("Garder la valeur mesurée (Échap)");
    const more = document.createElement("button");
    more.textContent = "…";
    more.title = t("Nom et expression de la cote");
    box.append(input, unitEl, ok, cancel, more);
    host.appendChild(box);
    const left = Math.min(Math.max(at.x - rect.left + 12, 4),
      rect.width - box.offsetWidth - 4);
    const top = Math.min(Math.max(at.y - rect.top - box.offsetHeight - 12, 4),
      rect.height - box.offsetHeight - 4);
    box.style.left = `${left}px`;
    box.style.top = `${top}px`;
    modifyBox = box;

    const apply = () => {
      const extra = dimEditPayload({ value: input.value, name: dim.name ?? "" },
        sketchDim, { shown, isSketchAngle });
      closeModifyBox();
      if (extra.value === undefined && extra.expr === undefined) return;
      const params = { sketch: mode.state.sketch, dim: dim.id, ...extra };
      safe((async () => {
        const state = await call("sketch_set_dim", params);
        await refresh(call("get_tree"));
        return state;
      })(), { keepSelection: true });
    };
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        apply();
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeModifyBox();
      }
      event.stopPropagation();
    });
    ok.addEventListener("click", apply);
    cancel.addEventListener("click", closeModifyBox);
    more.addEventListener("click", () => {
      closeModifyBox();
      editDim(dim);
    });
    input.focus();
    input.select();
  }

  return { closeModifyBox, openModifyBox };
}
