import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/login"];

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  const token = req.cookies.get("token")?.value;

  if (!token && !isPublic && pathname !== "/") {
    const loginUrl = new URL("/login", req.url);
    return NextResponse.redirect(loginUrl);
  }
  if (token && pathname.startsWith("/login")) {
    return NextResponse.redirect(new URL("/analytics", req.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/analytics/:path*", "/dashboard/:path*", "/operations/:path*", "/settings/:path*", "/login"],
};
