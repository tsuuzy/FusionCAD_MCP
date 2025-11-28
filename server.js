// server.js
const express = require('express');
const { exec } = require('child_process');
const app = express();
app.use(express.json());

app.post('/mcp/fusion-command', (req, res) => {
  const { command } = req.body;
  exec(`python fusion_controller.py "${command}"`, (err, stdout) => {
    if (err) return res.status(500).send({ error: err.message });
    res.send({ result: stdout.trim() });
  });
});

app.listen(3000, () => console.log("Fusion MCP Server running at http://localhost:3000"));
