import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { parseColor, readScene, sceneColor } from "../../app/theme.js";

describe("thème de la scène", () => {
  it("rend la couleur de repli sans DOM", () => {
    assert.equal(sceneColor("selection", null), 0xd9924a);
    assert.equal(sceneColor("bg"), 0x17191c);
    assert.equal(readScene(null).accent, 0x4f8fdb);
  });

  it("lit une variable CSS en hex ou en rgb", () => {
    const style = {
      getPropertyValue(name) {
        if (name === "--selection") return " #ff8800 ";
        if (name === "--bg") return "rgb(10, 20, 30)";
        return "";
      },
    };
    assert.equal(sceneColor("selection", style), 0xff8800);
    assert.equal(sceneColor("bg", style), 0x0a141e);
    assert.equal(sceneColor("accent", style), 0x4f8fdb);
  });

  it("accepte un hex court", () => {
    assert.equal(parseColor("#abc"), 0xaabbcc);
    assert.equal(parseColor("pas une couleur"), null);
  });
});
