// ============================================================================
// ga4-pull  (v11.82)  -  the GA4 pull as a button, not two terminal commands
// ============================================================================
// Jason: "this should be a button press".
//
// The dashboard is a static file on GitHub Pages with no server, so the button
// needs somewhere to run. This is that somewhere: it does what
// smarterpaw-blog/ga4_pull.py and this repo's load_ga4.py do between them,
// in one call, with no machine of Jason's involved.
//
// ----------------------------------------------------------------------------
// /!\ THIS IS A PORT, AND A PORT IS A SECOND COPY OF A SPEC
// ----------------------------------------------------------------------------
// The metric list, the dimension map, the seven reports and their conflict
// keys are declared in ga4_pull.py and load_ga4.py as well as here. Three
// copies of one spec drift. `tests/test_v1182.py` parses all three and fails
// the build when they disagree - that assertion is the only thing making this
// duplication safe, so do not delete it when editing either side.
//
// ----------------------------------------------------------------------------
// /!\ WHY A SERVICE ACCOUNT RATHER THAN THE EXISTING TOKEN
// ----------------------------------------------------------------------------
// ga4_pull.py authenticates as JASON, with an OAuth refresh token sitting in
// smarterpaw-blog/ga4_token.json. That token is a user credential tied to one
// machine's file system; it is not something to copy into a cloud secret. A
// service account is the credential designed for this, and it is granted
// Viewer on the property explicitly rather than inheriting a person's access.
//
// ----------------------------------------------------------------------------
// /!\ A SHORT READ IS REFUSED, NOT WRITTEN
// ----------------------------------------------------------------------------
// ga4_pull.py raises rather than write a truncated report, because a short
// read is invisible downstream: every total built on it is simply low and
// nothing says so. Same rule here, per report.
//
// ----------------------------------------------------------------------------
// SECRETS (Supabase -> Edge Functions -> Secrets)
// ----------------------------------------------------------------------------
//   GA4_SA_JSON       the whole service-account JSON key file
//   GA4_PROPERTY_ID   363832203
// SUPABASE_URL and SUPABASE_ANON_KEY are injected by the platform. The
// service role is deliberately NOT used - see the note above upsert().
// ============================================================================

const SCOPE = "https://www.googleapis.com/auth/analytics.readonly";
const PROPERTY = "smarterpaw";
const SITE = "smarterpaw.com";

// The canonical metric set. GA4 allows 10 per request; this is 8.
// [apiName, columnName] - the column spelling is the one the tables use.
const METRICS: [string, string][] = [
  ["sessions", "sessions"],
  ["totalUsers", "total_users"],        // de-duped per row period; NEVER sum
  ["newUsers", "new_users"],
  ["engagedSessions", "engaged_sessions"],
  ["totalRevenue", "revenue"],
  ["transactions", "transactions"],
  ["totalPurchasers", "purchasers"],    // de-duped per row period; NEVER sum
  ["keyEvents", "key_events"],
];

// Landing pages carry only the metrics that are both additive AND meaningful
// per page. A de-duplicated user count per landing page per day would be a
// number nobody can roll up.
const PAGE_METRICS: [string, string][] = [
  ["sessions", "sessions"],
  ["newUsers", "new_users"],
  ["engagedSessions", "engaged_sessions"],
  ["totalRevenue", "revenue"],
  ["transactions", "transactions"],
];

const DIMS: Record<string, string> = {
  date: "day",
  yearMonth: "month",
  sessionDefaultChannelGroup: "channel",
  deviceCategory: "device",
  sessionSource: "source",
  sessionMedium: "medium",
  landingPage: "landing_page",
};

const NUM_COLS = new Set(["revenue"]);

// by_source_medium is DELIBERATELY ABSENT: it is a period aggregate with no
// date column, so loading it would put a figure in the database whose window
// is whatever the last pull happened to use (the v11.22 trap). load_ga4.py
// does not load it either.
type Report = {
  key: string;
  table: string;
  conflict: string;
  dims: string[];
  metrics: [string, string][];
  snapCol?: string;
};
const REPORTS: Report[] = [
  { key: "by_date", table: "ga4_by_date", conflict: "property,day",
    dims: ["date"], metrics: METRICS, snapCol: "date_rows" },
  // The MONTH ANCHOR. GA4 de-duplicates users inside whatever window it is
  // asked for, so a month row carries figures that summing days cannot
  // reproduce - and it pins sessions exactly for a month-aligned window.
  { key: "by_month", table: "ga4_by_month", conflict: "property,month",
    dims: ["yearMonth"], metrics: METRICS, snapCol: "month_rows" },
  { key: "by_month_channel", table: "ga4_by_month_channel",
    conflict: "property,month,channel",
    dims: ["yearMonth", "sessionDefaultChannelGroup"], metrics: METRICS },
  { key: "by_date_channel", table: "ga4_by_date_channel",
    conflict: "property,day,channel",
    dims: ["date", "sessionDefaultChannelGroup"], metrics: METRICS,
    snapCol: "channel_rows" },
  { key: "by_date_device", table: "ga4_by_date_device",
    conflict: "property,day,device",
    dims: ["date", "deviceCategory"], metrics: METRICS, snapCol: "device_rows" },
  { key: "by_date_landing_page", table: "ga4_by_date_landing_page",
    conflict: "property,day,landing_page,channel",
    dims: ["date", "landingPage", "sessionDefaultChannelGroup"],
    metrics: PAGE_METRICS, snapCol: "page_rows" },
];

const PAGE_SIZE = 100000;
const INSERT_BATCH = 2000;
// Edge Functions get 150s of wall clock on this plan. Stop cleanly before
// that rather than being killed mid-report with nothing said.
const BUDGET_MS = 115000;

// ---------------------------------------------------------------------------
// Google auth: service-account JWT -> access token.
// ---------------------------------------------------------------------------
function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlJson(o: unknown): string {
  return b64url(new TextEncoder().encode(JSON.stringify(o)));
}

async function importPrivateKey(pem: string): Promise<CryptoKey> {
  const body = pem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  const der = Uint8Array.from(atob(body), (c) => c.charCodeAt(0));
  return await crypto.subtle.importKey(
    "pkcs8",
    der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

async function googleAccessToken(sa: { client_email: string; private_key: string }): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const unsigned = b64urlJson({ alg: "RS256", typ: "JWT" }) + "." +
    b64urlJson({
      iss: sa.client_email,
      scope: SCOPE,
      aud: "https://oauth2.googleapis.com/token",
      iat: now,
      exp: now + 3600,
    });
  const key = await importPrivateKey(sa.private_key);
  const sig = new Uint8Array(await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(unsigned)));
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: unsigned + "." + b64url(sig),
    }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || !body.access_token) {
    // Name the likely cause: this fails for exactly two reasons and the
    // message from Google says neither of them plainly.
    throw new Error(
      "Google refused the service account (" + res.status + "): " +
      JSON.stringify(body).slice(0, 300) +
      " - check that the Google Analytics Data API is enabled on the project " +
      "and that " + sa.client_email + " has Viewer on the GA4 property.",
    );
  }
  return body.access_token as string;
}

// ---------------------------------------------------------------------------
// GA4 Data API.
// ---------------------------------------------------------------------------
// GA4 hands back 20261030 for a date and 202610 for a yearMonth. Normalise at
// the source so no downstream reader has to know that.
function fmtDim(dim: string, v: string): string {
  if (dim === "date" && /^\d{8}$/.test(v)) {
    return v.slice(0, 4) + "-" + v.slice(4, 6) + "-" + v.slice(6, 8);
  }
  if (dim === "yearMonth" && /^\d{6}$/.test(v)) {
    return v.slice(0, 4) + "-" + v.slice(4, 6);
  }
  return v;
}

async function runReport(
  token: string, propertyId: string, rep: Report, from: string, to: string,
): Promise<Record<string, string>[]> {
  const out: Record<string, string>[] = [];
  let offset = 0;
  let rowCount: number | null = null;
  for (;;) {
    const res = await fetch(
      "https://analyticsdata.googleapis.com/v1beta/properties/" + propertyId + ":runReport",
      {
        method: "POST",
        headers: {
          Authorization: "Bearer " + token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          dateRanges: [{ startDate: from, endDate: to }],
          dimensions: rep.dims.map((name) => ({ name })),
          metrics: rep.metrics.map(([name]) => ({ name })),
          limit: PAGE_SIZE,
          offset,
        }),
      },
    );
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(
        rep.key + ": GA4 returned " + res.status + " " +
        JSON.stringify(body?.error?.message ?? body).slice(0, 300),
      );
    }
    if (rowCount === null) rowCount = Number(body.rowCount || 0);
    const rows = body.rows || [];
    for (const r of rows) {
      const row: Record<string, string> = {};
      rep.dims.forEach((d, i) => {
        row[DIMS[d] ?? d] = fmtDim(d, r.dimensionValues?.[i]?.value ?? "");
      });
      rep.metrics.forEach(([, col], i) => {
        row[col] = r.metricValues?.[i]?.value ?? "";
      });
      out.push(row);
    }
    if (!rows.length || out.length >= (rowCount ?? 0)) break;
    offset += rows.length;
  }
  // /!\ A short read is invisible downstream - every total built on it is
  // simply low and nothing says so. Refuse rather than write it.
  if (rowCount && out.length !== rowCount) {
    throw new Error(
      "TRUNCATED report " + rep.key + ": collected " + out.length +
      " of " + rowCount + " rows. Refusing to write a short report.",
    );
  }
  return out;
}

// ---------------------------------------------------------------------------
// Supabase writes, through PostgREST with the service role.
// ---------------------------------------------------------------------------
function num(v: string, isFloat: boolean): number {
  // GA4 writes '' for a metric it has no value for. Every metric here is an
  // accumulated count or a sum, so an absent one really is zero.
  const t = String(v ?? "").trim();
  if (t === "") return 0;
  const n = Number(t);
  if (!Number.isFinite(n)) return 0;
  return isFloat ? n : Math.round(n);
}

// /!\ WRITES AS THE CALLER, NOT AS THE SERVICE ROLE.
//
// Not one table in this database grants service_role anything; all 52 grant
// `authenticated` only, because the app always signs in - and load_ga4.py,
// which this function ports, writes these exact tables that way today.
// Granting service_role would introduce the first such grant in the
// database, for one function, when the role making the request already has
// the privilege.
//
// A SCHEDULED run has no caller, so cron would need that grant added
// deliberately in the release that adds scheduling.
async function upsert(
  url: string, anonKey: string, bearer: string, table: string,
  conflict: string, rows: Record<string, unknown>[],
): Promise<void> {
  for (let i = 0; i < rows.length; i += INSERT_BATCH) {
    const chunk = rows.slice(i, i + INSERT_BATCH);
    const res = await fetch(
      url + "/rest/v1/" + table + "?on_conflict=" + encodeURIComponent(conflict),
      {
        method: "POST",
        headers: {
          apikey: anonKey,
          Authorization: bearer,
          "Content-Type": "application/json",
          Prefer: "resolution=merge-duplicates,return=minimal",
        },
        body: JSON.stringify(chunk),
      },
    );
    if (!res.ok) {
      const t = await res.text().catch(() => "");
      throw new Error(table + ": write failed (" + res.status + ") " + t.slice(0, 300));
    }
  }
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

// ---------------------------------------------------------------------------
Deno.serve(async (req: Request) => {
  // /!\ ECHO THE REQUESTED HEADERS. supabase-js sends Content-Type, so the
  // browser preflights for it; an Allow-Headers list that omits what was
  // asked for fails CORS, fetch REJECTS, and the client reports "failed to
  // send a request" with no status to debug from. Echoing cannot fall
  // behind whatever the client decides to send next.
  const asked = req.headers.get("access-control-request-headers");
  const cors = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": asked ||
      "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Max-Age": "86400",
  };
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });

  const started = Date.now();
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { ...cors, "Content-Type": "application/json" },
    });

  try {
    const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
    const anon = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
    const bearer = req.headers.get("authorization") ?? "";
    // /!\ THIS FUNCTION AUTHENTICATES ITS OWN CALLER.
    //
    // With the platform's Verify JWT on, the gateway can reject the CORS
    // preflight - which carries no Authorization header, by design - before
    // any of this runs, and its rejection has no CORS headers on it. The
    // browser then reports "failed to send a request", which is the same
    // message as a missing function and debugs like neither.
    //
    // So: deploy with Verify JWT OFF, and check here. It writes with the
    // service role, so it must not be open - and this check is correct
    // whether the platform's one is on or off.
    if (!bearer.toLowerCase().startsWith("bearer ")) {
      return json({ ok: false, error: "Not signed in: no bearer token on the request." }, 401);
    }
    if (SUPABASE_URL && anon) {
      const who = await fetch(SUPABASE_URL + "/auth/v1/user", {
        headers: { apikey: anon, Authorization: bearer },
      });
      if (!who.ok) {
        return json({ ok: false, error: "Not signed in: Supabase rejected the token (" + who.status + ")." }, 401);
      }
    }
    const propertyId = Deno.env.get("GA4_PROPERTY_ID") ?? "";
    const saRaw = Deno.env.get("GA4_SA_JSON") ?? "";
    const missing = [
      !SUPABASE_URL && "SUPABASE_URL",
      !Deno.env.get("SUPABASE_ANON_KEY") && "SUPABASE_ANON_KEY",
      !propertyId && "GA4_PROPERTY_ID",
      !saRaw && "GA4_SA_JSON",
    ].filter(Boolean);
    if (missing.length) {
      return json({ ok: false, error: "Missing secret(s): " + missing.join(", ") }, 500);
    }

    let sa: { client_email: string; private_key: string };
    try {
      sa = JSON.parse(saRaw);
    } catch {
      return json({ ok: false, error: "GA4_SA_JSON is not valid JSON. Paste the whole key file." }, 500);
    }
    if (!sa.client_email || !sa.private_key) {
      return json({ ok: false, error: "GA4_SA_JSON has no client_email / private_key." }, 500);
    }

    // The window. 30 days by default: GA4 does not restate beyond ~48h, so a
    // month re-settles everything that could have moved, and a 400-day
    // backfill would not finish inside one invocation.
    let days = 30;
    try {
      const body = await req.json();
      if (body && Number.isFinite(Number(body.days))) {
        days = Math.max(2, Math.min(400, Math.floor(Number(body.days))));
      }
    } catch { /* no body: keep the default */ }

    const from = daysAgo(days);
    const to = today();
    const snapshotDate = to;

    const token = await googleAccessToken(sa);

    const counts: Record<string, number> = {};
    const done: string[] = [];
    let stoppedEarly: string | null = null;
    let total = 0;

    for (const rep of REPORTS) {
      if (Date.now() - started > BUDGET_MS) {
        stoppedEarly = rep.key;
        break;
      }
      const raw = await runReport(token, propertyId, rep, from, to);
      const rows = raw.map((r) => {
        const row: Record<string, unknown> = {
          property: PROPERTY,
          snapshot_date: snapshotDate,
        };
        for (const d of rep.dims) {
          const col = DIMS[d] ?? d;
          row[col] = r[col] ?? "";
        }
        for (const [, col] of rep.metrics) row[col] = num(r[col], NUM_COLS.has(col));
        return row;
      });
      await upsert(SUPABASE_URL, anon, bearer, rep.table, rep.conflict, rows);
      counts[rep.key] = rows.length;
      done.push(rep.table);
      total += rows.length;
    }

    // The pull row, so the Uploads page can say when this last ran. Written
    // even on an early stop: it DID pull, and the row is what makes that
    // visible (v11.73 - how far the data reaches and when it was last pulled
    // are different questions).
    const snap: Record<string, unknown> = {
      property: PROPERTY,
      property_id: String(propertyId),
      site: SITE,
      snapshot_date: snapshotDate,
      window_start: from,
      window_end: to,
      pulled_at: new Date().toISOString(),
    };
    for (const rep of REPORTS) {
      if (rep.snapCol) snap[rep.snapCol] = counts[rep.key] ?? 0;
    }
    await upsert(SUPABASE_URL, anon, bearer, "ga4_snapshots", "property,snapshot_date", [snap]);

    return json({
      ok: true,
      window: { from, to, days },
      rows: total,
      counts,
      tables: done,
      seconds: Math.round((Date.now() - started) / 1000),
      stoppedEarly,
      note: stoppedEarly
        ? "Stopped before " + stoppedEarly + " to stay inside the time budget. " +
          "Run it again, or pass fewer days."
        : null,
    });
  } catch (e) {
    return json({
      ok: false,
      error: String((e as Error)?.message ?? e),
      seconds: Math.round((Date.now() - started) / 1000),
    }, 500);
  }
});
