const fs = require('fs');

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
  console.error('Usage: node ua-tour-analyze.js <input.json> <output.json>');
  process.exit(1);
}

let data;
try {
  data = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
} catch (e) {
  console.error('Failed to read/parse input:', e.message);
  process.exit(1);
}

const { nodes, edges, layers } = data;

// Build lookup maps
const nodeMap = {};
for (const n of nodes) {
  nodeMap[n.id] = n;
}

// A. Fan-In Ranking
const fanIn = {};
const fanOut = {};
for (const n of nodes) {
  fanIn[n.id] = 0;
  fanOut[n.id] = 0;
}
for (const e of edges) {
  if (fanIn[e.target] !== undefined) fanIn[e.target]++;
  if (fanOut[e.source] !== undefined) fanOut[e.source]++;
}

const fanInRanking = Object.entries(fanIn)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 20)
  .map(([id, count]) => ({ id, fanIn: count, name: nodeMap[id]?.name || id }));

// B. Fan-Out Ranking
const fanOutRanking = Object.entries(fanOut)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 20)
  .map(([id, count]) => ({ id, fanOut: count, name: nodeMap[id]?.name || id }));

// C. Entry Point Candidates
const totalNodes = nodes.length;
const fanOutValues = Object.values(fanOut).sort((a, b) => a - b);
const fanInValues = Object.values(fanIn).sort((a, b) => a - b);
const top10PctFanOut = fanOutValues[Math.floor(totalNodes * 0.9)] || 0;
const bottom25PctFanIn = fanInValues[Math.floor(totalNodes * 0.25)] || 0;

const entryPatterns = [
  'index.ts','index.js','main.ts','main.js','app.ts','app.js',
  'server.ts','server.js','mod.rs','main.go','main.py','main.rs',
  'manage.py','app.py','wsgi.py','asgi.py','run.py','__main__.py',
  'Application.java','Main.java','Program.cs','config.ru','index.php',
  'App.swift','Application.kt','main.cpp','main.c'
];

const scores = {};
for (const n of nodes) {
  let score = 0;
  if (n.type === 'document') {
    if (n.name === 'README.md' && (n.filePath === 'README.md' || n.filePath === './README.md')) {
      score += 5;
    } else if (n.name.endsWith('.md') && !n.filePath.includes('/')) {
      score += 2;
    }
  } else {
    const baseName = n.name;
    if (entryPatterns.includes(baseName)) score += 3;
    const depth = (n.filePath || '').split('/').length - 1;
    if (depth <= 1) score += 1;
    if (fanOut[n.id] >= top10PctFanOut) score += 1;
    if (fanIn[n.id] <= bottom25PctFanIn) score += 1;
  }
  scores[n.id] = score;
}

const entryPointCandidates = Object.entries(scores)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 5)
  .map(([id, score]) => ({
    id,
    score,
    name: nodeMap[id]?.name || id,
    summary: nodeMap[id]?.summary || ''
  }));

// D. BFS from top CODE entry point
const topCodeEntry = entryPointCandidates.find(c => nodeMap[c.id]?.type === 'file');
const bfsStart = topCodeEntry ? topCodeEntry.id : null;

const bfsOrder = [];
const depthMap = {};
const byDepth = {};

if (bfsStart) {
  // Build adjacency for imports/calls
  const adj = {};
  for (const n of nodes) adj[n.id] = [];
  for (const e of edges) {
    if ((e.type === 'imports' || e.type === 'calls') && adj[e.source]) {
      adj[e.source].push(e.target);
    }
  }

  const visited = new Set();
  const queue = [{ id: bfsStart, depth: 0 }];
  visited.add(bfsStart);

  while (queue.length > 0) {
    const { id, depth } = queue.shift();
    bfsOrder.push(id);
    depthMap[id] = depth;
    if (!byDepth[depth]) byDepth[depth] = [];
    byDepth[depth].push(id);

    for (const neighbor of (adj[id] || [])) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        queue.push({ id: neighbor, depth: depth + 1 });
      }
    }
  }
}

// E. Non-code files
const nonCodeFiles = { documentation: [], infrastructure: [], data: [], config: [] };
for (const n of nodes) {
  if (n.type === 'document') {
    nonCodeFiles.documentation.push({ id: n.id, name: n.name, summary: n.summary });
  } else if (['service','pipeline','resource'].includes(n.type)) {
    nonCodeFiles.infrastructure.push({ id: n.id, name: n.name, type: n.type, summary: n.summary });
  } else if (['table','schema','endpoint'].includes(n.type)) {
    nonCodeFiles.data.push({ id: n.id, name: n.name, type: n.type, summary: n.summary });
  } else if (n.type === 'config') {
    nonCodeFiles.config.push({ id: n.id, name: n.name, summary: n.summary });
  }
}

// F. Tightly coupled clusters
const edgeSet = new Set(edges.map(e => `${e.source}|||${e.target}`));
const bidirectionalPairs = [];
for (const e of edges) {
  const reverse = `${e.target}|||${e.source}`;
  if (edgeSet.has(reverse) && e.source < e.target) {
    bidirectionalPairs.push([e.source, e.target]);
  }
}

// Build clusters by expanding bidirectional pairs
const clusters = [];
for (const pair of bidirectionalPairs) {
  clusters.push({ nodes: [...pair], edgeCount: 2 });
}

// Expand clusters: add nodes connected to 2+ cluster members
for (const cluster of clusters) {
  for (const n of nodes) {
    if (cluster.nodes.includes(n.id)) continue;
    let connections = 0;
    for (const member of cluster.nodes) {
      if (edgeSet.has(`${n.id}|||${member}`) || edgeSet.has(`${member}|||${n.id}`)) {
        connections++;
      }
    }
    if (connections >= 2) {
      cluster.nodes.push(n.id);
      cluster.edgeCount += connections;
    }
  }
}

// G. Layers
const layerInfo = {
  count: layers.length,
  list: layers.map(l => ({ id: l.id, name: l.name, description: l.description }))
};

// H. Node summary index
const nodeSummaryIndex = {};
for (const n of nodes) {
  nodeSummaryIndex[n.id] = { name: n.name, type: n.type, summary: n.summary };
}

const result = {
  scriptCompleted: true,
  entryPointCandidates,
  fanInRanking,
  fanOutRanking,
  bfsTraversal: {
    startNode: bfsStart,
    order: bfsOrder,
    depthMap,
    byDepth
  },
  nonCodeFiles,
  clusters: clusters.slice(0, 10),
  layers: layerInfo,
  nodeSummaryIndex,
  totalNodes: nodes.length,
  totalEdges: edges.length
};

try {
  fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
} catch (e) {
  console.error('Failed to write output:', e.message);
  process.exit(1);
}

console.log('Analysis complete.');
process.exit(0);
