import "server-only";
import { cookies } from "next/headers";

const base = process.env.BACKEND_INTERNAL_URL?.trim().replace(/\/+$/, "");
if (!base) {
  throw new Error("BACKEND_INTERNAL_URL must be set");
}

/** Calls the backend from the server, forwarding the signed-in user's cookie. */
export async function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const cookieHeader = (await cookies()).toString();
  return fetch(`${base}${path}`, {
    ...init,
    headers: { ...init.headers, cookie: cookieHeader },
    cache: "no-store",
  });
}
