// Esquisse : la saisie numérique pendant le tracé (longueur, angle,
// rayon…), ouverte en tapant un chiffre.

import { t } from "../i18n.js";
import { numericDrawTarget, numericFields } from "../geom2d.js";
import { num } from "../num.js";

export function installSaisie(sk) {
  const {
    renderer, say, mode, clearInference, placeDrawPoint, pendingDrawPoint,
    dimTyped,
  } = sk;

  // Saisie numérique : taper un chiffre pendant le tracé ouvre, près du
  // curseur, les cotes de l'entité (longueur et angle, rayon, largeur et
  // hauteur). Tab passe au champ suivant, Entrée pose, Échap renonce.
  let numericBox = null;

  function closeNumericEntry() {
    numericBox?.remove();
    numericBox = null;
  }

  function openNumericEntry(firstKey) {
    const pending = pendingDrawPoint();
    const labels = numericFields(mode.tool);
    if (!pending || !labels.length) return;
    closeNumericEntry();
    const host = renderer.domElement.parentElement;
    const box = document.createElement("div");
    box.className = "dim-modify sk-numeric";
    box.dataset.ownKeys = "";
    const inputs = labels.map((label, index) => {
      const field = document.createElement("label");
      field.append(t(label) + " ");
      const input = document.createElement("input");
      input.type = "text";
      input.inputMode = "decimal";
      if (index === 0) input.value = firstKey;
      field.append(input);
      box.append(field);
      return input;
    });
    const rect = host.getBoundingClientRect();
    const at = mode.lastMouse ?? { clientX: rect.left + rect.width / 2,
                                   clientY: rect.top + rect.height / 2 };
    box.style.left = `${at.clientX - rect.left + 16}px`;
    box.style.top = `${at.clientY - rect.top + 18}px`;
    host.appendChild(box);
    numericBox = box;
    const tool = mode.tool;
    const apply = async () => {
      const [a, b] = inputs.map((input) => num(input.value) ?? NaN);
      const target = numericDrawTarget(tool, pendingDrawPoint(),
        mode.lastLocal, a, b);
      closeNumericEntry();
      if (!target) {
        say("Saisie numérique : valeur invalide", true);
        return;
      }
      if (mode.tool !== tool) return;
      clearInference();
      if (sk.previewLine) sk.previewLine.visible = false;
      const before = new Set((mode.state?.entities ?? []).map((e) => e.id));
      await placeDrawPoint({ ...target, onPoint: false });
      await dimTyped(tool, before, a, b);
    };
    box.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.key === "Enter") {
        event.preventDefault();
        apply();
      } else if (event.key === "Escape") {
        event.preventDefault();
        closeNumericEntry();
      }
    });
    inputs[0].focus();
    inputs[0].setSelectionRange(firstKey.length, firstKey.length);
  }

  return { closeNumericEntry, openNumericEntry };
}
