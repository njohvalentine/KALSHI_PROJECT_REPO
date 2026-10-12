import { NextResponse, type NextRequest } from "next/server";

// Convenience redirect only: it looks for the cookie, it does not prove the session is valid.
// The backend rejects every request without a valid session, and pages call verifySession().
export function proxy(request: NextRequest) {
  const hasCookie = request.cookies.has("session");
  const onLogin = request.nextUrl.pathname === "/login";
  if (!hasCookie && !onLogin) return NextResponse.redirect(new URL("/login", request.url));
  if (hasCookie && onLogin) return NextResponse.redirect(new URL("/games", request.url));
  return NextResponse.next();
}

export const config = {
  // Not for the proxied backend paths, Next.js internals or files with an extension.
  matcher: ["/((?!auth|api|_next/static|_next/image|.*\\..*).*)"],
};
