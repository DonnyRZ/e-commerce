import { colorHex, mediaUrl, pickLocalized, toCardProduct } from "./localize";

describe("localization helpers", () => {
  test("prefers the requested locale and falls back to English", () => {
    expect(pickLocalized({ id: { title: "Kerudung" }, en: { title: "Hijab" } }, "id")).toBe("Kerudung");
    expect(pickLocalized({ en: { title: "Hijab" } }, "ru")).toBe("Hijab");
  });

  test("resolves relative media through the configured API origin", () => {
    process.env.REACT_APP_BACKEND_URL = "https://api.example.com/";
    expect(mediaUrl("/api/v1/cms/media/file/a.jpg")).toBe("https://api.example.com/api/v1/cms/media/file/a.jpg");
    expect(mediaUrl("https://cdn.example.com/a.jpg")).toBe("https://cdn.example.com/a.jpg");
  });

  test("maps catalog data to a storefront card", () => {
    const card = toCardProduct(
      {
        id: "p1",
        slug: "hijab",
        translations: { en: { title: "Hijab" } },
        media: [{ url: "/hijab.jpg" }],
        base_price: 100000,
        compare_at_price: 120000,
        brand: "MC",
        colors: ["black"],
      },
      "en",
    );
    expect(card).toMatchObject({ id: "p1", name: "Hijab", badge: "sale", href: "/product/hijab" });
    expect(colorHex("black")).toBe("#1A1A1A");
  });
});
