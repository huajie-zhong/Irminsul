const { lateFee } = require("./fees");

function plainFee(days) {
  return lateFee(days);
}

module.exports = {
  handler() {
    return plainFee(1);
  },
};
