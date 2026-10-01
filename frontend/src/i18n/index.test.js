import { getLocalePreference } from "./index";

describe("locale preference precedence", () => {
  beforeEach(() => window.localStorage.clear());

  test("keeps an explicitly selected store locale ahead of the account locale", () => {
    window.localStorage.setItem("mc_locale", "ru");

    expect(getLocalePreference("uz")).toBe("ru");
  });

  test("uses the account locale when the browser has no saved selection", () => {
    expect(getLocalePreference("uz")).toBe("uz");
  });

  test("ignores an unsupported browser locale and uses a supported account locale", () => {
    window.localStorage.setItem("mc_locale", "fr");

    expect(getLocalePreference("uz")).toBe("uz");
  });
});
