// Loaded only from a temporary staged snapshot. Supply the ORM boundary while
// keeping the controller, helper functions and error-to-status mapping intact.
const fs = require("node:fs");
const path = require("node:path");

let writes;
const models = {
  Tag: {}, User: {},
  Article: {
    async findOne() { return null; },
    async create(fields) {
      writes.push(fields.title);
      return {
        ...fields, dataValues: { ...fields }, setAuthor() {},
        async hasUser() { return false; }, async countUsers() { return 0; },
      };
    },
  },
};

const modelPath = path.resolve("backend/models.js");
fs.writeFileSync(modelPath, "");
require.cache[modelPath] = { exports: models };
console.log = () => {}; // The app logs error details, which are not part of the gate output.
const { createArticle } = require("./backend/controllers/articles.js");
const handleError = require("./backend/middleware/errorHandler.js");

async function exercise(title, valid) {
  writes = [];
  const req = {
    loggedUser: {
      dataValues: {}, async hasFollower() { return false; }, async countFollowers() { return 0; },
    },
    body: { article: { title, description: "description", body: "body", tagList: [] } },
  };
  let responseCode = 200;
  let sent = false;
  const res = {
    status(code) { responseCode = code; return this; },
    json() { sent = true; return this; },
  };
  const expected = valid ? "201, 제목을 유지해 1회 생성" : "400 또는 422, 생성 0회";
  try {
    await createArticle(req, res, (error) => handleError(error, req, res));
  } catch {
    return { input: title, expected, actual: { error: "컨트롤러 실행 오류" }, status: "unchecked" };
  }
  const actual = { response: sent ? responseCode : null, modelCreateCalls: writes.length };
  let status = "unchecked";
  if (sent && responseCode < 500) {
    const matched = valid
      ? responseCode === 201 && writes.length === 1 && writes[0] === title
      : [400, 422].includes(responseCode) && writes.length === 0;
    status = matched ? "pass" : "fail";
  }
  return { input: title, expected, actual, status };
}

async function main() {
  const cases = [];
  for (const title of ["", "   ", "Conduit probe article"]) {
    cases.push(await exercise(title, title.trim().length > 0));
  }
  process.stdout.write(JSON.stringify(cases));
}
main().catch(() => { process.exitCode = 1; });
