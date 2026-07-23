const {
  proxyJson
} = require("../../_sembiotic_proxy");

module.exports = function handler(req, res) {
  return proxyJson(
    req,
    res,
    "/field/v1/health",
    ["GET", "HEAD"],
    20000
  );
};
