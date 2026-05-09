import { request } from '@playwright/test';

export async function probeBackendHealth(baseURL: string): Promise<boolean> {
  const ctx = await request.newContext();
  try {
    const res = await ctx.get(`${baseURL}/health`);
    return res.ok();
  } finally {
    await ctx.dispose();
  }
}
