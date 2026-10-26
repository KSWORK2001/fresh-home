#!/usr/bin/env node
/* Sign a Tizen TV widget directory and package it as a .wgt.

Pipeline replicates the Samsung Tizen TV extension (tizensdk.tizentv)
byte-for-byte: same SignedInfo layout, same constant #prop digests, same
exclusive C14N quirks — signed with a locally generated author certificate
(Tizen Developer CA) and the sdk-public distributor identity.

Usage: node sign.js <projectRoot> <output.wgt>
*/

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execSync } = require('child_process');

const EXT = '/Users/karan/.vscode/extensions/tizensdk.tizentv-1.3.3';
const forge = require(EXT + '/node_modules/node-forge');
const Dom = require(EXT + '/node_modules/xmldom').DOMParser;
const { ExclusiveCanonicalization } = require('./exclusive-canonicalization');

const CG = '/Users/karan/tizentv-tools/certificate-generator';
const CA_KEY = CG + '/certificates/developer/tizen-developer-ca-privatekey.pem';
const CA_CER = CG + '/certificates/developer/tizen-developer-ca.cer';
const CA_PWD = 'tizencertificatefordevelopercaroqkfwk';
const DIST_P12 = CG + '/certificates/distributor/sdk-public/tizen-distributor-signer.p12';
const DIST_CA = CG + '/certificates/distributor/sdk-public/tizen-distributor-ca.cer';
const DIST_PWD = 'tizenpkcs12passfordsigner';

const CERTS_DIR = path.join(__dirname, 'certs');
const AUTHOR_P12 = path.join(CERTS_DIR, 'author.p12');
const AUTHOR_PWD = 'freshhome-tv-signing';
const AUTHOR_NAME = 'MacLauncher';

const authorPropDgst = 'lpo8tUDs054eLlBQXiDPVDVKfw30ZZdtkRs1jd7H5K8=';
const distributorPropDgst = 'u/jU3U4Zm5ihTMSjKGlGYbWzDfRkGphPPHx3gJIYEJ4=';

// ---- p12 parsing (logic from the extension's cryptUtil) --------------------

function pemToB64(pem) {
  const b = '-----BEGIN CERTIFICATE-----';
  const e = '-----END CERTIFICATE-----';
  return pem.substring(pem.indexOf(b) + b.length + 1, pem.indexOf(e));
}

function parseP12(file, password) {
  const der = fs.readFileSync(file).toString('binary');
  const p12 = forge.pkcs12.pkcs12FromAsn1(forge.asn1.fromDer(der), password);
  const out = { privateKey: '', certChain: [] };
  p12.safeContents.forEach(sc => sc.safeBags.forEach(bag => {
    if (bag.type === forge.pki.oids.certBag) {
      out.certChain.push(pemToB64(forge.pki.certificateToPem(bag.cert)));
    } else if (bag.type === forge.pki.oids.pkcs8ShroudedKeyBag) {
      const key = forge.pki.privateKeyToPem(bag.key);
      out.privateKey = key.substring(key.indexOf('-----BEGIN RSA PRIVATE KEY-----'));
    }
  }));
  return out;
}

// ---- one-time author certificate (mirrors TizenCertManager.createCert) -----

function ensureAuthorCert() {
  if (fs.existsSync(AUTHOR_P12)) return;
  fs.mkdirSync(CERTS_DIR, { recursive: true });

  const keys = forge.pki.rsa.generateKeyPair(2048);
  const cert = forge.pki.createCertificate();
  cert.publicKey = keys.publicKey;
  cert.serialNumber = '01';
  cert.validity.notBefore = new Date();
  const notAfter = new Date();
  notAfter.setFullYear(notAfter.getFullYear() + 8);
  cert.validity.notAfter = notAfter;

  cert.setSubject([{ name: 'commonName', value: AUTHOR_NAME }]);
  cert.setIssuer([
    { name: 'organizationName', value: 'Tizen Association' },
    { shortName: 'OU', value: 'Tizen Association' },
    { shortName: 'CN', value: 'Tizen Developers CA' },
  ]);
  cert.setExtensions([
    { name: 'basicConstraints', cA: true },
    { name: 'keyUsage', keyCertSign: true, digitalSignature: true,
      nonRepudiation: true, keyEncipherment: true, dataEncipherment: true },
    { name: 'extKeyUsage', codeSigning: true },
  ]);

  const caKey = forge.pki.decryptRsaPrivateKey(
    fs.readFileSync(CA_KEY, 'utf8'), CA_PWD);
  cert.sign(caKey);

  const userCert = forge.pki.certificateToPem(cert);
  const caCert = fs.readFileSync(CA_CER, 'utf8'); // PEM

  const asn1 = forge.pkcs12.toPkcs12Asn1(
    keys.privateKey, [userCert, caCert], AUTHOR_PWD,
    { generateLocalKeyId: true, friendlyName: AUTHOR_NAME });
  fs.writeFileSync(AUTHOR_P12,
    forge.asn1.toDer(asn1).getBytes(), { encoding: 'binary' });
  console.log('generated author certificate:', AUTHOR_P12);
}

// ---- signature construction (verbatim from the extension's packageSigner) --

class Reference {
  constructor(uri) { this.uri = uri; this.digestValue = ''; }
  digest(content) {
    if (this.uri == '#prop') {
      this.digestValue = content;
    } else {
      const shasum = crypto.createHash('sha256');
      shasum.update(content, 'utf8');
      this.digestValue = shasum.digest('base64');
    }
  }
  getElement() {
    const transform = `<Transforms>\n` +
      `<Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"></Transform>\n` +
      `</Transforms>\n`;
    return `<Reference URI="${this.uri}">\n` +
      `${this.uri == '#prop' ? transform : ''}` +
      `<DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"></DigestMethod>\n` +
      `<DigestValue>${this.digestValue}</DigestValue>\n` +
      `</Reference>\n`;
  }
}

class Signature {
  constructor(id, projectRoot) {
    this.id = id;
    this.projectRoot = projectRoot;
    this.signedInfo = '';
    this.signatureValue = '';
    this.keyInfo = '';
  }
  _listFiles() {
    const dirList = [];
    const excludeFile = this.id == 'AuthorSignature'
      ? ['author-signature.xml', 'signature1.xml', 'signature2.xml']
      : ['signature1.xml', 'signature2.xml'];
    (function walk(curDir) {
      fs.readdirSync(curDir, { withFileTypes: true }).forEach(item => {
        if (!item.name.startsWith('.') && !excludeFile.includes(item.name)) {
          if (item.isDirectory()) walk(path.resolve(curDir, item.name));
          else dirList.push(path.resolve(curDir, item.name));
        }
      });
    })(this.projectRoot);
    return dirList.sort();
  }
  _addReferences(fileList) {
    let references = '';
    fileList.forEach(file => {
      const uri = encodeURIComponent(
        file.substring(this.projectRoot.length + 1).replace(/\\/g, '/'));
      const ref = new Reference(uri);
      ref.digest(fs.readFileSync(file));
      references += `${ref.getElement()}`;
    });
    const propRef = new Reference('#prop');
    propRef.digest(this.id == 'AuthorSignature' ? authorPropDgst : distributorPropDgst);
    references += `${propRef.getElement()}`;
    return references;
  }
  sign(key) {
    const references = this._addReferences(this._listFiles());
    this.signedInfo = '<SignedInfo>\n' +
      '<CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"></CanonicalizationMethod>\n' +
      '<SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"></SignatureMethod>\n' +
      `${references}` +
      '</SignedInfo>\n';

    const signWrapper =
      `<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">${this.signedInfo}</Signature>`;
    const xml = new Dom().parseFromString(signWrapper);
    const node = xml.documentElement.firstChild;
    const canoned = new ExclusiveCanonicalization().process(node,
      { defaultNsForPrefix: { ds: 'http://www.w3c.org/2000/09/xmldsig#' } });

    const signer = crypto.createSign('RSA-SHA256');
    signer.update(canoned);
    const sigValue = signer.sign(key, 'base64');
    this.signatureValue =
      `<SignatureValue>\n${sigValue}\n</SignatureValue>\n`;
  }
  addKeyInfo(certChain) {
    this.keyInfo = `<KeyInfo>\n<X509Data>\n`;
    certChain.forEach(cert => {
      this.keyInfo += `<X509Certificate>${cert}</X509Certificate>\n`;
    });
    this.keyInfo += `</X509Data>\n</KeyInfo>\n`;
  }
  generateSignatureXml() {
    const role = this.id == 'AuthorSignature' ? 'author' : 'distributor';
    return `<Signature xmlns="http://www.w3.org/2000/09/xmldsig#" Id="${this.id}">\n` +
      `${this.signedInfo}` +
      `${this.signatureValue}` +
      `${this.keyInfo}` +
      `<Object Id="prop"><SignatureProperties xmlns:dsp="http://www.w3.org/2009/xmldsig-properties"><SignatureProperty Id="profile" Target="#${this.id}"><dsp:Profile URI="http://www.w3.org/ns/widgets-digsig#profile"></dsp:Profile></SignatureProperty><SignatureProperty Id="role" Target="#${this.id}"><dsp:Role URI="http://www.w3.org/ns/widgets-digsig#role-${role}"></dsp:Role></SignatureProperty><SignatureProperty Id="identifier" Target="#${this.id}"><dsp:Identifier></dsp:Identifier></SignatureProperty></SignatureProperties></Object>\n` +
      `</Signature>`;
  }
}

// ---- package ---------------------------------------------------------------

function quote(p) { return `"${p}"`; }

function packageWgt(root, out, authorOnly) {
  const files = [];
  (function walk(dir) {
    fs.readdirSync(dir, { withFileTypes: true }).forEach(item => {
      if (item.name.startsWith('.') ||
          ['author-signature.xml', 'signature1.xml', 'signature2.xml'].includes(item.name)) return;
      const p = path.join(dir, item.name);
      if (item.isDirectory()) walk(p);
      else files.push(path.relative(root, p));
    });
  })(root);
  const order = ['config.xml', 'author-signature.xml']
    .concat(authorOnly ? [] : ['signature1.xml'])
    .concat(files.sort().filter(f => f !== 'config.xml'));
  execSync(`cd ${quote(root)} && rm -f ${quote(out)} && zip -X -q ${quote(out)} ${order.map((f) => quote(f)).join(' ')}`);
}

function main() {
  const [root, out] = process.argv.slice(2);
  if (!root || !out) {
    console.error('usage: node sign.js <projectRoot> <output.wgt>');
    process.exit(1);
  }

  // Samsung-issued certs (from make_samsung_cert.py) take priority —
  // 2024+ TVs reject the free SDK developer certificate.
  const samsungDir = path.join(__dirname, 'certs', 'samsung');
  let author, dist;
  if (fs.existsSync(path.join(samsungDir, 'author.p12'))) {
    const pwd = fs.readFileSync(path.join(samsungDir, 'password.txt'), 'utf8').trim();
    author = parseP12(path.join(samsungDir, 'author.p12'), pwd);
    dist = parseP12(path.join(samsungDir, 'distributor.p12'), pwd);
    console.log(`using Samsung-issued certificates (author chain ${author.certChain.length}, distributor chain ${dist.certChain.length})`);
  } else {
    ensureAuthorCert();
    author = parseP12(AUTHOR_P12, AUTHOR_PWD);
    console.log(`author: ${author.certChain.length} certs in chain`);
    dist = parseP12(DIST_P12, DIST_PWD);
    if (dist.certChain.length < 2) {
      dist.certChain.push(pemToB64(fs.readFileSync(DIST_CA, 'utf8')));
    }
    console.log(`distributor: ${dist.certChain.length} certs in chain`);
  }

  const a = new Signature('AuthorSignature', root);
  a.sign(author.privateKey);
  a.addKeyInfo(author.certChain);
  fs.writeFileSync(path.join(root, 'author-signature.xml'),
    a.generateSignatureXml(), 'utf8');

  const authorOnly = process.env.AUTHOR_ONLY === '1';
  if (!authorOnly) {
    const d = new Signature('DistributorSignature', root);
    d.sign(dist.privateKey);
    d.addKeyInfo(dist.certChain);
    fs.writeFileSync(path.join(root, 'signature1.xml'),
      d.generateSignatureXml(), 'utf8');
  }

  packageWgt(root, path.resolve(out), authorOnly);
  fs.unlinkSync(path.join(root, 'author-signature.xml'));
  if (!authorOnly) fs.unlinkSync(path.join(root, 'signature1.xml'));
  console.log('signed:', out, authorOnly ? '(author-only)' : '');
}

main();
