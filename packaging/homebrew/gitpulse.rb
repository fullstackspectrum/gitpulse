# Template for Formula/gitpulse.rb in fullstackspectrum/homebrew-gitpulse.
# The release workflow renders it with packaging/homebrew/render_formula.py,
# which fills in the sdist url and sha256 and the resource blocks from PyPI.
# Edit everything else here rather than in the tap.
class Gitpulse < Formula
  include Language::Python::Virtualenv

  desc "GitHub traffic, clones, referrers, and release downloads with HTML dashboards"
  homepage "https://github.com/fullstackspectrum/gitpulse"
  url "@URL@"
  sha256 "@SHA256@"
  license "MIT"

  depends_on "python@3.13"

  @RESOURCES@

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/gitpulse --version")
    assert_match "No GitHub token found", shell_output("#{bin}/gitpulse repos 2>&1", 1)
  end
end
