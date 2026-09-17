import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const target = process.argv[2] === "cms" ? "cms" : "storefront";
const cracoBin = fileURLToPath(
  new URL("../node_modules/@craco/craco/dist/bin/craco.js", import.meta.url),
);

const result = spawnSync(
  process.execPath,
  [cracoBin, "build"],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      FRONTEND_TARGET: target,
      PUBLIC_URL: target === "cms" ? "/admin" : "",
    },
  },
);

if (result.error) {
  throw result.error;
}

process.exit(result.status ?? 1);
