export const prerender = true

export function GET() {
  return new Response(
    JSON.stringify({
      status: 'ok',
      build_sha: process.env.BUILD_SHA || 'not-provided',
    }),
    {
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
      },
    },
  )
}
