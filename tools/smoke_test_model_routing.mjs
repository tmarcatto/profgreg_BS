import fs from "node:fs/promises";
import path from "node:path";
import {
  loadLocalEnv,
  loadModelRouting,
  resolveModelRole,
  validateProviderEnvironment,
} from "../workspace/adapters/model-router.mjs";

const OUT_DIR = path.resolve("runs/_system/api_smoke_tests");
const OUT_FILE = path.join(OUT_DIR, "latest_api_smoke_test.json");
const LOG_FILE = path.join(OUT_DIR, "api_smoke_test_log.jsonl");

const DEFAULT_TEXT_ROLES = [
  "course_architect",
  "source_research",
  "pedagogy_review",
  "localization",
  "diagram_rendering",
];

function nowIso() {
  return new Date().toISOString();
}

function sanitizeError(error) {
  const raw = String(error?.message ?? error ?? "Unknown error");
  return raw
    .replace(/sk-[A-Za-z0-9_-]+/g, "[redacted]")
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, "Bearer [redacted]")
    .slice(0, 1200);
}

async function writeJson(pathname, data) {
  await fs.mkdir(path.dirname(pathname), { recursive: true });
  await fs.writeFile(pathname, JSON.stringify(data, null, 2) + "\n");
}

async function appendJsonl(pathname, data) {
  await fs.mkdir(path.dirname(pathname), { recursive: true });
  await fs.appendFile(pathname, JSON.stringify(data) + "\n");
}

async function callOpenAiText({ model, apiKey, baseUrl }) {
  const endpoint = `${baseUrl.replace(/\/$/, "")}/responses`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      input: "Reply with exactly: Prof Greg route OK",
      max_output_tokens: 16,
    }),
  });

  const body = await response.text();
  if (!response.ok) {
    throw new Error(`OpenAI API ${response.status}: ${body}`);
  }

  const parsed = JSON.parse(body);
  const text =
    parsed.output_text ??
    parsed.output?.flatMap((item) => item.content ?? [])
      ?.map((content) => content.text ?? "")
      ?.join("") ??
    "";

  return {
    ok: true,
    response_excerpt: text.slice(0, 80),
  };
}

async function callOpenAiCompatibleText({ model, apiKey, baseUrl, providerLabel }) {
  const endpoint = `${baseUrl.replace(/\/$/, "")}/chat/completions`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      messages: [
        {
          role: "user",
          content: "Reply with exactly: Prof Greg route OK",
        },
      ],
      max_tokens: 16,
      temperature: 0,
    }),
  });

  const body = await response.text();
  if (!response.ok) {
    throw new Error(`${providerLabel} API ${response.status}: ${body}`);
  }

  const parsed = JSON.parse(body);
  const message = parsed.choices?.[0]?.message ?? {};
  const text = message.content ?? message.reasoning_content ?? parsed.output_text ?? "";

  return {
    ok: true,
    response_excerpt: text.slice(0, 80),
  };
}

async function callAnthropicText({ model, apiKey, baseUrl }) {
  const endpoint = `${baseUrl.replace(/\/$/, "")}/v1/messages`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      max_tokens: 16,
      messages: [
        {
          role: "user",
          content: "Reply with exactly: Prof Greg route OK",
        },
      ],
    }),
  });

  const body = await response.text();
  if (!response.ok) {
    throw new Error(`Anthropic API ${response.status}: ${body}`);
  }

  const parsed = JSON.parse(body);
  const text = (parsed.content ?? [])
    .map((item) => item.text ?? "")
    .join("");

  return {
    ok: true,
    response_excerpt: text.slice(0, 80),
  };
}

async function callOpenAiImage({ model, apiKey, baseUrl }) {
  const endpoint = `${baseUrl.replace(/\/$/, "")}/images/generations`;
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      prompt: "A simple clean icon of a blueprint sheet and a pencil, flat vector style.",
      size: "1024x1024",
      n: 1,
    }),
  });

  const body = await response.text();
  if (!response.ok) {
    throw new Error(`OpenAI Images API ${response.status}: ${body}`);
  }

  const parsed = JSON.parse(body);
  return {
    ok: true,
    image_items: Array.isArray(parsed.data) ? parsed.data.length : 0,
  };
}

async function testResolvedRole(role, resolved, env, options = {}) {
  const envCheck = validateProviderEnvironment(resolved, env);
  const selected = resolved.selection;
  const provider = resolved.provider_name;
  const model = selected.model ?? selected.engine;
  const baseUrlEnv = resolved.provider?.base_url_env;
  const apiKeyEnv = resolved.provider?.api_key_env;
  const baseUrl = baseUrlEnv && env[baseUrlEnv]
    ? env[baseUrlEnv]
    : provider === "openai"
      ? "https://api.openai.com/v1"
      : provider === "anthropic"
        ? "https://api.anthropic.com"
        : provider === "deepseek"
          ? "https://api.deepseek.com"
          : provider === "xai"
            ? "https://api.x.ai/v1"
        : null;

  const started = nowIso();
  const common = {
    role,
    provider,
    model,
    started,
    quality_gate: resolved.quality_gate,
  };

  if (!envCheck.ok) {
    return {
      ...common,
      status: "missing_key",
      missing: envCheck.missing,
    };
  }

  if (provider === "local_deterministic") {
    return {
      ...common,
      status: "pass",
      mode: "local_no_api",
      response_excerpt: "No API key required.",
    };
  }

  try {
    let result;
    if (provider === "openai" && role === "image_generation") {
      if (!options.includeImage) {
        return {
          ...common,
          status: "skipped",
          reason: "Image generation skipped by default to avoid image-generation cost. Re-run with --include-image.",
        };
      }
      result = await callOpenAiImage({
        model,
        apiKey: env[apiKeyEnv],
        baseUrl,
      });
    } else if (provider === "openai") {
      result = await callOpenAiText({
        model,
        apiKey: env[apiKeyEnv],
        baseUrl,
      });
    } else if (provider === "anthropic") {
      result = await callAnthropicText({
        model,
        apiKey: env[apiKeyEnv],
        baseUrl,
      });
    } else if (provider === "deepseek" || provider === "xai") {
      result = await callOpenAiCompatibleText({
        model,
        apiKey: env[apiKeyEnv],
        baseUrl,
        providerLabel: provider,
      });
    } else {
      return {
        ...common,
        status: "skipped",
        reason: `No smoke-test handler implemented for provider ${provider}.`,
      };
    }

    return {
      ...common,
      status: "pass",
      ...result,
      finished: nowIso(),
    };
  } catch (error) {
    return {
      ...common,
      status: "fail",
      error: sanitizeError(error),
      finished: nowIso(),
    };
  }
}

async function testRole(role, env, options = {}) {
  const resolved = await resolveModelRole(role);
  return testResolvedRole(role, resolved, env, options);
}

async function testCandidate(candidate, env, options = {}) {
  const config = await loadModelRouting();
  const provider = config.providers?.[candidate.provider];
  if (!provider) {
    return {
      role: candidate.role,
      provider: candidate.provider,
      model: candidate.model,
      status: "fail",
      error: `Unknown provider ${candidate.provider}`,
    };
  }

  return testResolvedRole(
    candidate.role,
    {
      role: candidate.role,
      provider_name: candidate.provider,
      provider,
      selection: {
        provider: candidate.provider,
        model: candidate.model,
      },
      fallbacks: [],
      quality_gate: "candidate_smoke_test",
    },
    env,
    options,
  );
}

function parseArgs(argv) {
  const includeImage = argv.includes("--include-image");
  const includeCandidates = argv.includes("--include-candidates");
  const roleFlagIndex = argv.indexOf("--roles");
  const roles = roleFlagIndex === -1
    ? DEFAULT_TEXT_ROLES
    : argv[roleFlagIndex + 1].split(",").map((role) => role.trim()).filter(Boolean);

  if (includeImage && !roles.includes("image_generation")) {
    roles.push("image_generation");
  }

  return { includeImage, includeCandidates, roles };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  await loadModelRouting();
  const envSource = await loadLocalEnv();
  const results = [];

  for (const role of options.roles) {
    const result = await testRole(role, envSource.env, options);
    results.push(result);
    await appendJsonl(LOG_FILE, result);
  }

  if (options.includeCandidates) {
    const candidates = [
      { role: "candidate_deepseek_flash", provider: "deepseek", model: "deepseek-v4-flash" },
      { role: "candidate_deepseek_pro", provider: "deepseek", model: "deepseek-v4-pro" },
      { role: "candidate_grok_4_5", provider: "xai", model: "grok-4.5" },
    ];
    for (const candidate of candidates) {
      const result = await testCandidate(candidate, envSource.env, options);
      results.push(result);
      await appendJsonl(LOG_FILE, result);
    }
  }

  const summary = {
    created_at: nowIso(),
    env_file_loaded: envSource.loaded,
    include_image: options.includeImage,
    include_candidates: options.includeCandidates,
    roles_requested: options.roles,
    counts: results.reduce((acc, item) => {
      acc[item.status] = (acc[item.status] ?? 0) + 1;
      return acc;
    }, {}),
    results,
  };

  await writeJson(OUT_FILE, summary);

  const publicSummary = {
    created_at: summary.created_at,
    include_image: summary.include_image,
    counts: summary.counts,
    results: results.map((item) => ({
      role: item.role,
      provider: item.provider,
      model: item.model,
      status: item.status,
      reason: item.reason,
      missing: item.missing,
      error: item.error,
      response_excerpt: item.response_excerpt,
    })),
    report: OUT_FILE,
  };

  console.log(JSON.stringify(publicSummary, null, 2));
}

main().catch((error) => {
  console.error(sanitizeError(error));
  process.exit(1);
});
