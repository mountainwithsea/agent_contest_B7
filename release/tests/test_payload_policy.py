import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('build_payload',Path(__file__).parents[1]/'build_payload.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)


class PayloadPolicyTests(unittest.TestCase):
    def test_runtime_is_preserved_but_install_and_training_files_are_not(self):
        root='shared/runtime/anystyle/rubyinstaller-3.3.12-2-x64/'
        keep=['bin/ruby.exe','bin/x64-ucrt-ruby330.dll','bin/ruby_builtin_dlls/libcrypto-3-x64.dll',
              'lib/ruby/3.3.0/json.rb','lib/ruby/3.3.0/x64-mingw-ucrt/date_core.so',
              'lib/ruby/gems/3.3.0/gems/rexml-3.4.4/lib/rexml/document.rb',
              'lib/ruby/gems/3.3.0/extensions/x64-mingw-ucrt/3.3.0/racc-1.7.3/racc/cparse.so']
        drop=['include/ruby-3.3.0/ruby.h','lib/libx64-ucrt-ruby330.dll.a','packages/foo',
              'share/ri/help','lib/ruby/gems/3.3.0/gems/rbs-3.4.0/lib/rbs.rb','lib/ruby/3.3.0/bundler.rb']
        for name in keep:self.assertTrue(build.include_payload(root+name),name)
        for name in drop:self.assertFalse(build.include_payload(root+name),name)
        for name in ['shared/runtime/node/node.exe','shared/runtime/anystyle/anystyle-1.5.0.gem',
                     'shared/runtime/anystyle/anystyle-1.5.0/res/parser.mod',
                     'runtime/reference/Lib/site-packages/_pytest/main.py']:
            self.assertFalse(build.include_payload(name),name)
        self.assertTrue(build.include_payload('licenses/AnyStyle-LICENSE'))
        self.assertTrue(build.include_payload('shared/runtime/anystyle/anystyle-1.5.0/lib/anystyle/parser.rb'))


if __name__=='__main__':unittest.main()
