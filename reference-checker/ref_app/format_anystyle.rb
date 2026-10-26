# Conversion-only adapter. Upstream normalizers/CSL formatter remain unmodified.
# No CRF model, native Wapiti extension, web request, or training is loaded.
require 'json'
require 'forwardable'
require 'logger'
root = File.expand_path(ENV['B7_ANYSTYLE_HOME'] || '../../shared/runtime/anystyle', __dir__)
%w[anystyle-1.5.0 wapiti-2.1.0 namae-1.2.0 citeproc-1.0.10 concurrent-ruby-1.2.2 i18n-1.14.1 tzinfo-2.0.6 zeitwerk-2.6.12 builder-3.2.4 edtf-3.1.1 activesupport-6.1.7.6].each { |p| $LOAD_PATH.unshift(File.join(root,p,'lib')) }
$LOAD_PATH.unshift(File.join(root,'concurrent-ruby-1.2.2/lib/concurrent-ruby'))
require 'active_support/core_ext/hash/keys'
require 'edtf'
require 'citeproc'
require 'wapiti/errors'
require 'wapiti/token'
require 'wapiti/sequence'
require 'wapiti/dataset'
require 'anystyle/support'
require 'anystyle/utils'
require 'anystyle/normalizer'
Dir[File.join(root,'anystyle-1.5.0/lib/anystyle/normalizer/*.rb')].sort.each { |p| require p }
%w[bibtex csl].each { |p| require "anystyle/format/#{p}" }
require 'anystyle/parser'

# The native CLD3 Ruby extension is unavailable here. Record exactly the sample
# requested by the upstream Locale normalizer for local CLD3 WebAssembly.
class AnyStyle::Normalizer::Locale
  attr_reader :last_sample
  def detect_language(text)
    @last_sample = text
    nil
  end
end

# Use the upstream initializer's normalizer order, without loading a CRF model.
source = File.read(File.join(root,'anystyle-1.5.0/lib/anystyle/parser.rb'))
names = source.match(/@normalizers = \[(.*?)\]/m)[1].scan(/Normalizer::(\w+)\.new/).flatten
normalizers = names.map { |name| AnyStyle::Normalizer.const_get(name).new }
parser = AnyStyle::Parser.allocate
parser.instance_variable_set(:@normalizers, normalizers)
locale = normalizers.find { |n| n.is_a?(AnyStyle::Normalizer::Locale) }
input = JSON.parse(STDIN.read)
sequences = input.map { |segments| Wapiti::Sequence.new(segments.map { |tag,value| Wapiti::Token.new(value,label:tag) }) }
samples=[]
# Preserve cross-reference normalizer context by formatting the entire dataset.
original = locale.method(:normalize)
locale.define_singleton_method(:normalize) do |item, **opts|
  @last_sample = nil
  value=original.call(item, **opts)
  samples << @last_sample
  value
end
csl=parser.format_csl(Wapiti::Dataset.new(sequences),date_format:'citeproc')
STDOUT.write(JSON.generate({csl:csl,locale_samples:samples,normalizers:names}))
