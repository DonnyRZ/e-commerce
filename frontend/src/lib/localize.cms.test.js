import { pickCmsLocalized } from "./localize";

describe("pickCmsLocalized", () => {
  test("uses a completed locale first", () => {
    expect(pickCmsLocalized({ en: { title: "Title" }, id: { title: "Judul" } }, "id")).toBe("Judul");
  });

  test("falls back to English when the requested locale is missing or blank", () => {
    const translations = { en: { title: "English title" }, id: { title: "" } };
    expect(pickCmsLocalized(translations, "id")).toBe("English title");
    expect(pickCmsLocalized(translations, "uz")).toBe("English title");
  });

  test("does not silently fall back to another incomplete locale", () => {
    expect(pickCmsLocalized({ id: { title: "Judul" }, ru: { title: "" } }, "ru")).toBe("");
  });

  test("treats whitespace-only English text as empty", () => {
    expect(pickCmsLocalized({ en: { title: "   " } }, "id")).toBe("");
  });
});
