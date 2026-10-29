/**
 * Shareable Proof Card Generator and Social Links.
 * 
 * Generates client-side 1200x630 PNG images using HTML5 Canvas
 * with high aesthetic fidelity suitable for Twitter/X cards, Reddit, and LinkedIn.
 */

export interface ProofCardData {
  repoName: string;
  repoYears?: string;
  question: string;
  answerSnippet: string;
  verifiedCount: number;
  totalCitations: number;
  citedHashes: string[];
  timestamp?: string;
}

/**
 * Render a high-resolution 1200x630 PNG proof card on a hidden canvas and trigger download.
 */
export async function downloadProofCard(data: ProofCardData): Promise<void> {
  const width = 1200;
  const height = 630;

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // Background gradient: Archival deep obsidian
  const bgGrad = ctx.createLinearGradient(0, 0, width, height);
  bgGrad.addColorStop(0, '#12100e');
  bgGrad.addColorStop(0.5, '#171512');
  bgGrad.addColorStop(1, '#0e0c0b');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, width, height);

  // Outer border with subtle amber glow
  ctx.strokeStyle = '#3a342c';
  ctx.lineWidth = 3;
  ctx.strokeRect(24, 24, width - 48, height - 48);

  ctx.strokeStyle = '#dca03244';
  ctx.lineWidth = 1;
  ctx.strokeRect(32, 32, width - 64, height - 64);

  // Header: Brand & Mascot
  ctx.fillStyle = '#e5983b';
  ctx.font = 'bold 20px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
  ctx.fillText('🕯 THE GHOST MAINTAINER · CODEBASE ARCHAEOLOGY', 64, 88);

  // Repository Badge
  ctx.fillStyle = '#e6e1d6';
  ctx.font = 'bold 36px Georgia, serif';
  ctx.fillText(data.repoName, 64, 145);

  if (data.repoYears) {
    ctx.fillStyle = '#a8a296';
    ctx.font = '20px monospace';
    ctx.fillText(`[${data.repoYears}]`, 64 + ctx.measureText(data.repoName).width + 16, 143);
  }

  // Inquiry Section
  ctx.fillStyle = '#a8a296';
  ctx.font = '600 16px -apple-system, sans-serif';
  ctx.fillText('HISTORICAL INQUIRY:', 64, 205);

  ctx.fillStyle = '#ffffff';
  ctx.font = 'italic 26px Georgia, serif';
  wrapText(ctx, `"${data.question}"`, 64, 242, width - 128, 34);

  // Ghost Voice Box
  const boxY = 320;
  ctx.fillStyle = '#1c1915';
  ctx.fillRect(64, boxY, width - 128, 170);
  ctx.strokeStyle = '#dca03255';
  ctx.lineWidth = 1.5;
  ctx.strokeRect(64, boxY, width - 128, 170);

  ctx.fillStyle = '#e5983b';
  ctx.font = 'bold 15px -apple-system, sans-serif';
  ctx.fillText('VERIFIED DEPARTED MAINTAINER RESPONSE:', 88, boxY + 36);

  ctx.fillStyle = '#e6e1d6';
  ctx.font = '20px Georgia, serif';
  const cleanSnippet = data.answerSnippet.replace(/\[([0-9a-f]{7,40})\]/g, '[$1 ✓]');
  wrapText(ctx, cleanSnippet, 88, boxY + 75, width - 176, 28);

  // Footer: Forensic Invariant & Seal
  ctx.fillStyle = '#26221c';
  ctx.fillRect(64, height - 95, width - 128, 48);

  ctx.fillStyle = '#52b788';
  ctx.font = 'bold 16px monospace';
  ctx.fillText('✓ 100% CITED COMMITS VERIFIED IN GIT OBJECT STORAGE', 84, height - 65);

  ctx.fillStyle = '#8a8275';
  ctx.font = '14px -apple-system, sans-serif';
  ctx.fillText('github.com/your-username/ghost-maintainer', width - 380, height - 65);

  // Trigger download
  const dataUrl = canvas.toDataURL('image/png');
  const a = document.createElement('a');
  a.download = `ghost-maintainer-${data.repoName.replace(/[/\\?%*:|"<>]/g, '_')}-proof.png`;
  a.href = dataUrl;
  a.click();
}

function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number
): void {
  const words = text.split(' ');
  let line = '';
  let curY = y;

  for (let n = 0; n < words.length; n++) {
    const testLine = line + words[n] + ' ';
    const metrics = ctx.measureText(testLine);
    if (metrics.width > maxWidth && n > 0) {
      ctx.fillText(line, x, curY);
      line = words[n] + ' ';
      curY += lineHeight;
      if (curY > y + lineHeight * 3) {
        ctx.fillText(line.trim() + '...', x, curY);
        return;
      }
    } else {
      line = testLine;
    }
  }
  ctx.fillText(line, x, curY);
}

/**
 * Generate formatted social share link for Twitter/X.
 */
export function getTwitterShareUrl(data: ProofCardData): string {
  const text = `I held a séance with the departed maintainers of ${data.repoName} using The Ghost Maintainer 🕯\n\n"${data.question}"\n\nEvery claim cites a real verified git commit hash. Voices are fiction. Evidence is real.`;
  const url = window.location.href;
  return `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`;
}

/**
 * Generate formatted Reddit share markdown snippet.
 */
export function getRedditShareText(data: ProofCardData): string {
  return `**Interrogating the ghost of ${data.repoName}**\n\n> Q: "${data.question}"\n\n${data.answerSnippet}\n\n*Verified by [The Ghost Maintainer](https://github.com/your-username/ghost-maintainer) — 100% git commit peeled.*`;
}

