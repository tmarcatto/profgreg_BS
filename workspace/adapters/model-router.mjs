import fs from "node:fs/promises";
import path from "node:path";

const DEFAULT_CONFIG = path.resolve("workspace/config/model-routing.json");
const DEFAULT_ENV_FILE = path.resolve(".env.local");

export async function loadLocalEnv(envPath = DEFAULT_ENV_FILE, baseEnv = process.env) {
  const nextEnv = { ...baseEnv };

  let raw;
  try {
    raw = await fs.readFile(envPath, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") {
      return {
        env: nextEnv,
        loaded: false,
        path: envPath,
      };
    }
    throw error;
  }

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;

    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    if (key && value && !nextEnv[key]) {
      nextEnv[key] = value;
    }
  }

  return {
    env: nextEnv,
    loaded: true,
    path: envPath,
  };
}

export async function loadModelRouting(configPath = DEFAULT_CONFIG) {
  const raw = await fs.readFile(configPath, "utf8");
  return JSON.parse(raw);
}

export async function resolveModelRole(role, options = {}) {
  const config = await loadModelRouting(options.configPath);
  const binding = config.bindings?.[role];

  if (!binding) {
    throw new Error(`Unknown model role: ${role}`);
  }

  const selected = binding.primary;
  const provider = config.providers?.[selected.provider];

  if (!provider) {
    throw new Error(`Unknown provider for role ${role}: ${selected.provider}`);
  }

  return {
    role,
    provider_name: selected.provider,
    provider,
    selection: selected,
    fallbacks: binding.fallbacks ?? [],
    quality_gate: binding.quality_gate ?? null,
  };
}

export function validateProviderEnvironment(resolvedRole, env = process.env) {
  const keyName = resolvedRole.provider?.api_key_env;
  if (!keyName) {
    return {
      ok: true,
      missing: [],
      note: "No API key required for this provider.",
    };
  }

  if (env[keyName]) {
    return {
      ok: true,
      missing: [],
      note: `Environment variable ${keyName} is present.`,
    };
  }

  return {
    ok: false,
    missing: [keyName],
    note: `Environment variable ${keyName} is missing.`,
  };
}

export async function describeRole(role, options = {}) {
  const resolved = await resolveModelRole(role, options);
  const envSource = options.env
    ? { env: options.env, loaded: false, path: null }
    : await loadLocalEnv(options.envPath);
  const envCheck = validateProviderEnvironment(resolved, envSource.env);

  return {
    role: resolved.role,
    provider: resolved.provider_name,
    model: resolved.selection.model ?? resolved.selection.engine,
    quality_gate: resolved.quality_gate,
    env_file_loaded: envSource.loaded,
    env: envCheck,
  };
}

export async function diagnoseConfiguredRoles(options = {}) {
  const config = await loadModelRouting(options.configPath);
  const envSource = await loadLocalEnv(options.envPath);
  const results = [];

  for (const role of Object.keys(config.bindings ?? {})) {
    const resolved = await resolveModelRole(role, options);
    const envCheck = validateProviderEnvironment(resolved, envSource.env);
    results.push({
      role,
      provider: resolved.provider_name,
      model: resolved.selection.model ?? resolved.selection.engine,
      api_key_env: resolved.provider?.api_key_env ?? null,
      status: envCheck.ok ? "ready" : "missing_key",
      missing: envCheck.missing,
      quality_gate: resolved.quality_gate,
    });
  }

  return {
    env_file_loaded: envSource.loaded,
    env_file_path: envSource.path,
    roles: results,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const role = process.argv[2];
  if (!role) {
    console.error("Usage: node workspace/adapters/model-router.mjs <role|--diagnose>");
    process.exit(2);
  }

  const command = role === "--diagnose" ? diagnoseConfiguredRoles() : describeRole(role);

  command
    .then((result) => {
      console.log(JSON.stringify(result, null, 2));
    })
    .catch((error) => {
      console.error(error.message);
      process.exit(1);
    });
}
