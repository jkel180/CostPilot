import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { getSupabaseConfig } from "@/lib/supabase/config";

/** Pages reachable without a session. */
const PUBLIC_PATHS = ["/login", "/signup", "/forgot-password", "/auth/callback"];
/** Pages a signed-in user should not see (sent to the app instead). */
const GUEST_ONLY = ["/login", "/signup"];

function matches(pathname: string, list: string[]) {
  return list.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * Refreshes the Supabase session cookie and performs optimistic redirects.
 * This is not the security boundary: the FastAPI backend verifies the token and the
 * organization membership on every request.
 */
export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const cfg = getSupabaseConfig();
  if (!cfg) {
    // Not configured yet: only the auth pages (which explain the setup) are usable.
    return matches(pathname, PUBLIC_PATHS)
      ? NextResponse.next()
      : NextResponse.redirect(new URL("/login", request.url));
  }

  let response = NextResponse.next({ request });
  const supabase = createServerClient(cfg.url, cfg.key, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (toSet) => {
        toSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        toSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
      },
    },
  });

  // getClaims() validates the JWT; do not use getSession() for server-side decisions.
  const { data } = await supabase.auth.getClaims();
  const signedIn = Boolean(data?.claims);

  const redirectTo = (path: string) => {
    const url = request.nextUrl.clone();
    url.pathname = path;
    url.search = path === "/login" && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
    const r = NextResponse.redirect(url);
    response.cookies.getAll().forEach((c) => r.cookies.set(c));
    return r;
  };

  if (!signedIn && !matches(pathname, PUBLIC_PATHS)) return redirectTo("/login");
  if (signedIn && matches(pathname, GUEST_ONLY)) return redirectTo("/dashboard");
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
