#!/usr/bin/python
# Copyright (c) 2016 The WebRTC project authors. All Rights Reserved.
#
# Use of this source code is governed by a BSD-style license
# that can be found in the LICENSE file in the root of the source
# tree. An additional intellectual property rights grant can be found
# in the file PATENTS.  All contributing project authors may
# be found in the AUTHORS file in the root of the source tree.

"""Tests for mb.py."""

import ast
import json
import StringIO
import os
import sys
import unittest

import mb


class FakeMBW(mb.MetaBuildWrapper):
  def __init__(self, win32=False):
    super(FakeMBW, self).__init__()

    # Override vars for test portability.
    if win32:
      self.src_dir = 'c:\\fake_src'
      self.default_config = 'c:\\fake_src\\tools-webrtc\\mb\\mb_config.pyl'
      self.default_isolate_map = ('c:\\fake_src\\testing\\buildbot\\'
                                  'gn_isolate_map.pyl')
      self.platform = 'win32'
      self.executable = 'c:\\python\\python.exe'
      self.sep = '\\'
    else:
      self.src_dir = '/fake_src'
      self.default_config = '/fake_src/tools-webrtc/mb/mb_config.pyl'
      self.default_isolate_map = '/fake_src/testing/buildbot/gn_isolate_map.pyl'
      self.executable = '/usr/bin/python'
      self.platform = 'linux2'
      self.sep = '/'

    self.files = {}
    self.calls = []
    self.cmds = []
    self.cross_compile = None
    self.out = ''
    self.err = ''
    self.rmdirs = []

  def ExpandUser(self, path):
    return '$HOME/%s' % path

  def Exists(self, path):
    return self.files.get(path) is not None

  def MaybeMakeDirectory(self, path):
    self.files[path] = True

  def PathJoin(self, *comps):
    return self.sep.join(comps)

  def ReadFile(self, path):
    return self.files[path]

  def WriteFile(self, path, contents, force_verbose=False):
    if self.args.dryrun or self.args.verbose or force_verbose:
      self.Print('\nWriting """\\\n%s""" to %s.\n' % (contents, path))
    self.files[path] = contents

  def Call(self, cmd, env=None, buffer_output=True):
    if env:
      self.cross_compile = env.get('GYP_CROSSCOMPILE')
    self.calls.append(cmd)
    if self.cmds:
      return self.cmds.pop(0)
    return 0, '', ''

  def Print(self, *args, **kwargs):
    sep = kwargs.get('sep', ' ')
    end = kwargs.get('end', '\n')
    f = kwargs.get('file', sys.stdout)
    if f == sys.stderr:
      self.err += sep.join(args) + end
    else:
      self.out += sep.join(args) + end

  def TempFile(self, mode='w'):
    return FakeFile(self.files)

  def RemoveFile(self, path):
    del self.files[path]

  def RemoveDirectory(self, path):
    self.rmdirs.append(path)
    files_to_delete = [f for f in self.files if f.startswith(path)]
    for f in files_to_delete:
      self.files[f] = None


class FakeFile(object):
  def __init__(self, files):
    self.name = '/tmp/file'
    self.buf = ''
    self.files = files

  def write(self, contents):
    self.buf += contents

  def close(self):
     self.files[self.name] = self.buf


TEST_CONFIG = """\
{
  'masters': {
    'chromium': {},
    'fake_master': {
      'fake_builder': 'gyp_rel_bot',
      'fake_gn_builder': 'gn_rel_bot',
      'fake_gyp_crosscompile_builder': 'gyp_crosscompile',
      'fake_gn_debug_builder': 'gn_debug_goma',
      'fake_gyp_builder': 'gyp_debug',
      'fake_gn_args_bot': '//build/args/bots/fake_master/fake_gn_args_bot.gn',
      'fake_memcheck_bot': 'gn_memcheck_bot',
      'fake_multi_phase': { 'phase_1': 'gn_phase_1', 'phase_2': 'gn_phase_2'},
      'fake_android_bot': 'gn_android_bot',
    },
  },
  'configs': {
    'gyp_rel_bot': ['gyp', 'rel', 'goma'],
    'gn_debug_goma': ['gn', 'debug', 'goma'],
    'gyp_debug': ['gyp', 'debug', 'fake_feature1'],
    'gn_rel_bot': ['gn', 'rel', 'goma'],
    'gyp_crosscompile': ['gyp', 'crosscompile'],
    'gn_phase_1': ['gn', 'phase_1'],
    'gn_phase_2': ['gn', 'phase_2'],
    'gn_memcheck_bot': ['gn', 'memcheck'],
    'gn_android_bot': ['gn', 'android'],
  },
  'mixins': {
    'crosscompile': {
      'gyp_crosscompile': True,
    },
    'fake_feature1': {
      'gn_args': 'enable_doom_melon=true',
      'gyp_defines': 'doom_melon=1',
    },
    'gyp': {'type': 'gyp'},
    'gn': {'type': 'gn'},
    'goma': {
      'gn_args': 'use_goma=true',
      'gyp_defines': 'goma=1',
    },
    'phase_1': {
      'gn_args': 'phase=1',
      'gyp_args': 'phase=1',
    },
    'phase_2': {
      'gn_args': 'phase=2',
      'gyp_args': 'phase=2',
    },
    'rel': {
      'gn_args': 'is_debug=false',
    },
    'debug': {
      'gn_args': 'is_debug=true',
    },
    'memcheck': {
      'gn_args': 'rtc_use_memcheck=true',
    },
    'android': {
      'gn_args': 'target_os="android"',
    }
  },
}
"""

GYP_HACKS_CONFIG = """\
{
  'masters': {
    'chromium': {},
    'fake_master': {
      'fake_builder': 'fake_config',
    },
  },
  'configs': {
    'fake_config': ['fake_mixin'],
  },
  'mixins': {
    'fake_mixin': {
      'type': 'gyp',
      'gn_args': '',
      'gyp_defines':
         ('foo=bar llvm_force_head_revision=1 '
          'gyp_link_concurrency=1 baz=1'),
    },
  },
}
"""


class UnitTest(unittest.TestCase):
  def fake_mbw(self, files=None, win32=False):
    mbw = FakeMBW(win32=win32)
    mbw.files.setdefault(mbw.default_config, TEST_CONFIG)
    mbw.files.setdefault(
      mbw.ToAbsPath('//testing/buildbot/gn_isolate_map.pyl'),
      '''{
        "foo_unittests": {
          "label": "//foo:foo_unittests",
          "type": "console_test_launcher",
          "args": [],
        },
      }''')
    mbw.files.setdefault(
        mbw.ToAbsPath('//build/args/bots/fake_master/fake_gn_args_bot.gn'),
        'is_debug = false\n')
    if files:
      for path, contents in files.items():
        mbw.files[path] = contents
    return mbw

  def check(self, args, mbw=None, files=None, out=None, err=None, ret=None):
    if not mbw:
      mbw = self.fake_mbw(files)

    actual_ret = mbw.Main(args)

    self.assertEqual(actual_ret, ret)
    if out is not None:
      self.assertEqual(mbw.out, out)
    if err is not None:
      self.assertEqual(mbw.err, err)
    return mbw

  def test_clobber(self):
    files = {
      '/fake_src/out/Debug': None,
      '/fake_src/out/Debug/mb_type': None,
    }
    mbw = self.fake_mbw(files)

    # The first time we run this, the build dir doesn't exist, so no clobber.
    self.check(['gen', '-c', 'gn_debug_goma', '//out/Debug'], mbw=mbw, ret=0)
    self.assertEqual(mbw.rmdirs, [])
    self.assertEqual(mbw.files['/fake_src/out/Debug/mb_type'], 'gn')

    # The second time we run this, the build dir exists and matches, so no
    # clobber.
    self.check(['gen', '-c', 'gn_debug_goma', '//out/Debug'], mbw=mbw, ret=0)
    self.assertEqual(mbw.rmdirs, [])
    self.assertEqual(mbw.files['/fake_src/out/Debug/mb_type'], 'gn')

    # Now we switch build types; this should result in a clobber.
    self.check(['gen', '-c', 'gyp_debug', '//out/Debug'], mbw=mbw, ret=0)
    self.assertEqual(mbw.rmdirs, ['/fake_src/out/Debug'])
    self.assertEqual(mbw.files['/fake_src/out/Debug/mb_type'], 'gyp')

    # Now we delete mb_type; this checks the case where the build dir
    # exists but wasn't populated by mb; this should also result in a clobber.
    del mbw.files['/fake_src/out/Debug/mb_type']
    self.check(['gen', '-c', 'gyp_debug', '//out/Debug'], mbw=mbw, ret=0)
    self.assertEqual(mbw.rmdirs,
                     ['/fake_src/out/Debug', '/fake_src/out/Debug'])
    self.assertEqual(mbw.files['/fake_src/out/Debug/mb_type'], 'gyp')

  def test_gn_analyze(self):
    files = {'/tmp/in.json': '''{\
               "files": ["foo/foo_unittest.cc"],
               "test_targets": ["foo_unittests"],
               "additional_compile_targets": ["all"]
             }''',
             '/tmp/out.json.gn': '''{\
               "status": "Found dependency",
               "compile_targets": ["//foo:foo_unittests"],
               "test_targets": ["//foo:foo_unittests"]
             }'''}

    mbw = self.fake_mbw(files)
    mbw.Call = lambda cmd, env=None, buffer_output=True: (0, '', '')

    self.check(['analyze', '-c', 'gn_debug_goma', '//out/Default',
                '/tmp/in.json', '/tmp/out.json'], mbw=mbw, ret=0)
    out = json.loads(mbw.files['/tmp/out.json'])
    self.assertEqual(out, {
      'status': 'Found dependency',
      'compile_targets': ['foo:foo_unittests'],
      'test_targets': ['foo_unittests']
    })

  def test_gn_gen(self):
    mbw = self.fake_mbw()
    self.check(['gen', '-c', 'gn_debug_goma', '//out/Default', '-g', '/goma'],
               mbw=mbw, ret=0)
    self.assertMultiLineEqual(mbw.files['/fake_src/out/Default/args.gn'],
                              ('goma_dir = "/goma"\n'
                               'is_debug = true\n'
                               'use_goma = true\n'))

    # Make sure we log both what is written to args.gn and the command line.
    self.assertIn('Writing """', mbw.out)
    self.assertIn('/fake_src/buildtools/linux64/gn gen //out/Default --check',
                  mbw.out)

    mbw = self.fake_mbw(win32=True)
    self.check(['gen', '-c', 'gn_debug_goma', '-g', 'c:\\goma', '//out/Debug'],
               mbw=mbw, ret=0)
    self.assertMultiLineEqual(mbw.files['c:\\fake_src\\out\\Debug\\args.gn'],
                              ('goma_dir = "c:\\\\goma"\n'
                               'is_debug = true\n'
                               'use_goma = true\n'))
    self.assertIn('c:\\fake_src\\buildtools\\win\\gn.exe gen //out/Debug '
                  '--check\n', mbw.out)

    mbw = self.fake_mbw()
    self.check(['gen', '-m', 'fake_master', '-b', 'fake_gn_args_bot',
                '//out/Debug'],
               mbw=mbw, ret=0)
    self.assertEqual(
        mbw.files['/fake_src/out/Debug/args.gn'],
        'import("//build/args/bots/fake_master/fake_gn_args_bot.gn")\n')


  def test_gn_gen_fails(self):
    mbw = self.fake_mbw()
    mbw.Call = lambda cmd, env=None, buffer_output=True: (1, '', '')
    self.check(['gen', '-c', 'gn_debug_goma', '//out/Default'], mbw=mbw, ret=1)

  def test_gn_gen_swarming(self):
    files = {
      '/tmp/swarming_targets': 'cc_perftests\n',
      '/fake_src/testing/buildbot/gn_isolate_map.pyl': (
          "{'cc_perftests': {"
          "  'label': '//cc:cc_perftests',"
          "  'type': 'console_test_launcher',"
          "}}\n"
      ),
      'c:\\fake_src\out\Default\cc_perftests.exe.runtime_deps': (
          "cc_perftests\n"
      ),
    }
    mbw = self.fake_mbw(files=files, win32=True)
    self.check(['gen',
                '-c', 'gn_debug_goma',
                '--swarming-targets-file', '/tmp/swarming_targets',
                '--isolate-map-file',
                '/fake_src/testing/buildbot/gn_isolate_map.pyl',
                '//out/Default'], mbw=mbw, ret=0)
    self.assertIn('c:\\fake_src\\out\\Default\\cc_perftests.isolate',
                  mbw.files)
    self.assertIn('c:\\fake_src\\out\\Default\\cc_perftests.isolated.gen.json',
                  mbw.files)

  def test_gn_gen_swarming_android(self):
    test_files = {
      '/tmp/swarming_targets': 'base_unittests\n',
      '/fake_src/testing/buildbot/gn_isolate_map.pyl': (
          "{'base_unittests': {"
          "  'label': '//base:base_unittests',"
          "  'type': 'additional_compile_target',"
          "}}\n"
      ),
      '/fake_src/out/Default/base_unittests.runtime_deps': (
          "base_unittests\n"
      ),
    }
    mbw = self.check(['gen', '-c', 'gn_android_bot', '//out/Default',
                      '--swarming-targets-file', '/tmp/swarming_targets',
                      '--isolate-map-file',
                      '/fake_src/testing/buildbot/gn_isolate_map.pyl'],
                     files=test_files, ret=0)

    isolate_file = mbw.files['/fake_src/out/Default/base_unittests.isolate']
    isolate_file_contents = ast.literal_eval(isolate_file)
    files = isolate_file_contents['variables']['files']
    command = isolate_file_contents['variables']['command']

    self.assertEqual(files, ['base_unittests'])
    self.assertEqual(command, [
        '../../build/android/test_wrapper/logdog_wrapper.py',
        '--target', 'base_unittests',
        '--logdog-bin-cmd', '../../bin/logdog_butler',
        '--target-devices-file', '${SWARMING_BOT_FILE}'
    ])

  def test_gn_gen_swarming_android_junit_test(self):
    test_files = {
      '/tmp/swarming_targets': 'base_unittests\n',
      '/fake_src/testing/buildbot/gn_isolate_map.pyl': (
          "{'base_unittests': {"
          "  'label': '//base:base_unittests',"
          "  'type': 'junit_test',"
          "}}\n"
      ),
      '/fake_src/out/Default/base_unittests.runtime_deps': (
          "base_unittests\n"
      ),
    }
    mbw = self.check(['gen', '-c', 'gn_android_bot', '//out/Default',
                      '--swarming-targets-file', '/tmp/swarming_targets',
                      '--isolate-map-file',
                      '/fake_src/testing/buildbot/gn_isolate_map.pyl'],
                     files=test_files, ret=0)

    isolate_file = mbw.files['/fake_src/out/Default/base_unittests.isolate']
    isolate_file_contents = ast.literal_eval(isolate_file)
    files = isolate_file_contents['variables']['files']
    command = isolate_file_contents['variables']['command']

    self.assertEqual(files, ['base_unittests'])
    self.assertEqual(command, [
        '../../build/android/test_wrapper/logdog_wrapper.py',
        '--target', 'base_unittests',
        '--logdog-bin-cmd', '../../bin/logdog_butler',
    ])

  def test_gn_gen_non_parallel_console_test_launcher(self):
    test_files = {
      '/tmp/swarming_targets': 'base_unittests\n',
      '/fake_src/testing/buildbot/gn_isolate_map.pyl': (
          "{'base_unittests': {"
          "  'label': '//base:base_unittests',"
          "  'type': 'non_parallel_console_test_launcher',"
          "}}\n"
      ),
      '/fake_src/out/Default/base_unittests.runtime_deps': (
          "base_unittests\n"
      ),
    }
    mbw = self.check(['gen', '-c', 'gn_debug_goma', '//out/Default',
                      '--swarming-targets-file', '/tmp/swarming_targets',
                      '--isolate-map-file',
                      '/fake_src/testing/buildbot/gn_isolate_map.pyl'],
                     files=test_files, ret=0)

    isolate_file = mbw.files['/fake_src/out/Default/base_unittests.isolate']
    isolate_file_contents = ast.literal_eval(isolate_file)
    files = isolate_file_contents['variables']['files']
    command = isolate_file_contents['variables']['command']

    self.assertEqual(files, [
        '../../testing/test_env.py',
        'base_unittests',
    ])
    self.assertEqual(command, [
        '../../testing/test_env.py',
        './base_unittests',
        '--',
        '--asan=0',
        '--msan=0',
        '--tsan=0',
    ])

  def test_gn_isolate_windowed_test_launcher_linux(self):
    test_files = {
      '/tmp/swarming_targets': 'base_unittests\n',
      '/fake_src/testing/buildbot/gn_isolate_map.pyl': (
          "{'base_unittests': {"
          "  'label': '//base:base_unittests',"
          "  'type': 'windowed_test_launcher',"
          "}}\n"
      ),
      '/fake_src/out/Default/base_unittests.runtime_deps': (
          "base_unittests\n"
          "some_resource_file\n"
      ),
    }
    mbw = self.check(['gen', '-c', 'gn_debug_goma', '//out/Default',
                      '--swarming-targets-file', '/tmp/swarming_targets',
                      '--isolate-map-file',
                      '/fake_src/testing/buildbot/gn_isolate_map.pyl'],
                     files=test_files, ret=0)

    isolate_file = mbw.files['/fake_src/out/Default/base_unittests.isolate']
    isolate_file_contents = ast.literal_eval(isolate_file)
    files = isolate_file_contents['variables']['files']
    command = isolate_file_contents['variables']['command']

    self.assertEqual(files, [
        '../../testing/test_env.py',
        '../../testing/xvfb.py',
        '../../third_party/gtest-parallel/gtest-parallel',
        '../../tools-webrtc/gtest-parallel-wrapper.py',
        'base_unittests',
        'some_resource_file',
    ])
    self.assertEqual(command, [
        '../../testing/xvfb.py',
        '../../tools-webrtc/gtest-parallel-wrapper.py',
        '--output_dir=${ISOLATED_OUTDIR}/test_logs',
        './base_unittests',
        '--',
        '--asan=0',
        '--msan=0',
        '--tsan=0',
    ])

  def test_gn_gen_windowed_test_launcher_win(self):
    files = {
      '/tmp/swarming_targets': 'unittests\n',
      '/fake_src/testing/buildbot/gn_isolate_map.pyl': (
          "{'unittests': {"
          "  'label': '//somewhere:unittests',"
          "  'type': 'windowed_test_launcher',"
          "}}\n"
      ),
      r'c:\fake_src\out\Default\unittests.exe.runtime_deps': (
          "unittests.exe\n"
          "some_dependency\n"
      ),
    }
    mbw = self.fake_mbw(files=files, win32=True)
    self.check(['gen',
                '-c', 'gn_debug_goma',
                '--swarming-targets-file', '/tmp/swarming_targets',
                '--isolate-map-file',
                '/fake_src/testing/buildbot/gn_isolate_map.pyl',
                '//out/Default'], mbw=mbw, ret=0)

    isolate_file = mbw.files['c:\\fake_src\\out\\Default\\unittests.isolate']
    isolate_file_contents = ast.literal_eval(isolate_file)
    files = isolate_file_contents['variables']['files']
    command = isolate_file_contents['variables']['command']

    self.assertEqual(files, [
        '../../testing/test_env.py',
        '../../third_party/gtest-parallel/gtest-parallel',
        '../../tools-webrtc/gtest-parallel-wrapper.py',
        'some_dependency',
        'unittests.exe',
    ])
    self.assertEqual(command, [
        '../../testing/test_env.py',
        '../../tools-webrtc/gtest-parallel-wrapper.py',
        '--output_dir=${ISOLATED_OUTDIR}\\test_logs',
        r'.\unittests.exe',
        '--',
        '--asan=0',
        '--msan=0',
        '--tsan=0',
    ])

  def test_gn_gen_console_test_launcher(self):
    test_files = {
      '/tmp/swarming_targets': 'base_unittests\n',
      '/fake_src/testing/buildbot/gn_isolate_map.pyl': (
          "{'base_unittests': {"
          "  'label': '//base:base_unittests',"
          "  'type': 'console_test_launcher',"
          "}}\n"
      ),
      '/fake_src/out/Default/base_unittests.runtime_deps': (
          "base_unittests\n"
      ),
    }
    mbw = self.check(['gen', '-c', 'gn_debug_goma', '//out/Default',
                      '--swarming-targets-file', '/tmp/swarming_targets',
                      '--isolate-map-file',
                      '/fake_src/testing/buildbot/gn_isolate_map.pyl'],
                     files=test_files, ret=0)

    isolate_file = mbw.files['/fake_src/out/Default/base_unittests.isolate']
    isolate_file_contents = ast.literal_eval(isolate_file)
    files = isolate_file_contents['variables']['files']
    command = isolate_file_contents['variables']['command']

    self.assertEqual(files, [
        '../../testing/test_env.py',
        '../../third_party/gtest-parallel/gtest-parallel',
        '../../tools-webrtc/gtest-parallel-wrapper.py',
        'base_unittests',
    ])
    self.assertEqual(command, [
        '../../testing/test_env.py',
        '../../tools-webrtc/gtest-parallel-wrapper.py',
        '--output_dir=${ISOLATED_OUTDIR}/test_logs',
        './base_unittests',
        '--',
        '--asan=0',
        '--msan=0',
        '--tsan=0',
    ])

  def test_gn_isolate_console_test_launcher_memcheck(self):
    test_files = {
      '/tmp/swarming_targets': 'base_unittests\n',
      '/fake_src/testing/buildbot/gn_isolate_map.pyl': (
          "{'base_unittests': {"
          "  'label': '//base:base_unittests',"
          "  'type': 'console_test_launcher',"
          "}}\n"
      ),
      '/fake_src/out/Release/base_unittests.runtime_deps': (
          "base_unittests\n"
          "lots_of_memcheck_dependencies\n"
          "../../tools-webrtc/valgrind/webrtc_tests.sh\n"
      ),
    }
    mbw = self.check(['gen', '-c', 'gn_memcheck_bot', '//out/Release',
                      '--swarming-targets-file', '/tmp/swarming_targets',
                      '--isolate-map-file',
                      '/fake_src/testing/buildbot/gn_isolate_map.pyl'],
                     files=test_files, ret=0)

    isolate_file = mbw.files['/fake_src/out/Release/base_unittests.isolate']
    isolate_file_contents = ast.literal_eval(isolate_file)
    files = isolate_file_contents['variables']['files']
    command = isolate_file_contents['variables']['command']

    self.assertEqual(files, [
        '../../testing/test_env.py',
        '../../tools-webrtc/valgrind/webrtc_tests.sh',
        'base_unittests',
        'lots_of_memcheck_dependencies',
    ])
    self.assertEqual(command, [
        '../../testing/test_env.py',
        'bash',
        '../../tools-webrtc/valgrind/webrtc_tests.sh',
        '--tool',
        'memcheck',
        '--target',
        'Release',
        '--build-dir',
        '..',
        '--test',
        './base_unittests',
        '--',
        '--asan=0',
        '--msan=0',
        '--tsan=0',
    ])

  def test_gn_isolate(self):
    files = {
      '/fake_src/out/Default/toolchain.ninja': "",
      '/fake_src/testing/buildbot/gn_isolate_map.pyl': (
          "{'base_unittests': {"
          "  'label': '//base:base_unittests',"
          "  'type': 'non_parallel_console_test_launcher',"
          "}}\n"
      ),
      '/fake_src/out/Default/base_unittests.runtime_deps': (
          "base_unittests\n"
      ),
    }
    self.check(['isolate', '-c', 'gn_debug_goma', '//out/Default',
                'base_unittests'], files=files, ret=0)

    # test running isolate on an existing build_dir
    files['/fake_src/out/Default/args.gn'] = 'is_debug = True\n'
    self.check(['isolate', '//out/Default', 'base_unittests'],
               files=files, ret=0)
    files['/fake_src/out/Default/mb_type'] = 'gn\n'
    self.check(['isolate', '//out/Default', 'base_unittests'],
               files=files, ret=0)

  def test_gn_run(self):
    files = {
      '/fake_src/testing/buildbot/gn_isolate_map.pyl': (
          "{'base_unittests': {"
          "  'label': '//base:base_unittests',"
          "  'type': 'windowed_test_launcher',"
          "}}\n"
      ),
      '/fake_src/out/Default/base_unittests.runtime_deps': (
          "base_unittests\n"
      ),
    }
    self.check(['run', '-c', 'gn_debug_goma', '//out/Default',
                'base_unittests'], files=files, ret=0)

  def test_gn_lookup(self):
    self.check(['lookup', '-c', 'gn_debug_goma'], ret=0)

  def test_gn_lookup_goma_dir_expansion(self):
    self.check(['lookup', '-c', 'gn_rel_bot', '-g', '/foo'], ret=0,
               out=('\n'
                    'Writing """\\\n'
                    'goma_dir = "/foo"\n'
                    'is_debug = false\n'
                    'use_goma = true\n'
                    '""" to _path_/args.gn.\n\n'
                    '/fake_src/buildtools/linux64/gn gen _path_\n'))

  def test_gyp_analyze(self):
    mbw = self.check(['analyze', '-c', 'gyp_rel_bot', '//out/Release',
                      '/tmp/in.json', '/tmp/out.json'], ret=0)
    self.assertIn('analyzer', mbw.calls[0])

  def test_gyp_crosscompile(self):
    mbw = self.fake_mbw()
    self.check(['gen', '-c', 'gyp_crosscompile', '//out/Release'],
               mbw=mbw, ret=0)
    self.assertTrue(mbw.cross_compile)

  def test_gyp_gen(self):
    self.check(['gen', '-c', 'gyp_rel_bot', '-g', '/goma', '//out/Release'],
               ret=0,
               out=("GYP_DEFINES='goma=1 gomadir=/goma'\n"
                    "python build/gyp_chromium -G output_dir=out\n"))

    mbw = self.fake_mbw(win32=True)
    self.check(['gen', '-c', 'gyp_rel_bot', '-g', 'c:\\goma', '//out/Release'],
               mbw=mbw, ret=0,
               out=("set GYP_DEFINES=goma=1 gomadir='c:\\goma'\n"
                    "python build\\gyp_chromium -G output_dir=out\n"))

  def test_gyp_gen_fails(self):
    mbw = self.fake_mbw()
    mbw.Call = lambda cmd, env=None, buffer_output=True: (1, '', '')
    self.check(['gen', '-c', 'gyp_rel_bot', '//out/Release'], mbw=mbw, ret=1)

  def test_gyp_lookup_goma_dir_expansion(self):
    self.check(['lookup', '-c', 'gyp_rel_bot', '-g', '/foo'], ret=0,
               out=("GYP_DEFINES='goma=1 gomadir=/foo'\n"
                    "python build/gyp_chromium -G output_dir=_path_\n"))

  def test_help(self):
    orig_stdout = sys.stdout
    try:
      sys.stdout = StringIO.StringIO()
      self.assertRaises(SystemExit, self.check, ['-h'])
      self.assertRaises(SystemExit, self.check, ['help'])
      self.assertRaises(SystemExit, self.check, ['help', 'gen'])
    finally:
      sys.stdout = orig_stdout

  def test_multiple_phases(self):
    # Check that not passing a --phase to a multi-phase builder fails.
    mbw = self.check(['lookup', '-m', 'fake_master', '-b', 'fake_multi_phase'],
                     ret=1)
    self.assertIn('Must specify a build --phase', mbw.out)

    # Check that passing a --phase to a single-phase builder fails.
    mbw = self.check(['lookup', '-m', 'fake_master', '-b', 'fake_gn_builder',
                      '--phase', 'phase_1'], ret=1)
    self.assertIn('Must not specify a build --phase', mbw.out)

    # Check that passing a wrong phase key to a multi-phase builder fails.
    mbw = self.check(['lookup', '-m', 'fake_master', '-b', 'fake_multi_phase',
                      '--phase', 'wrong_phase'], ret=1)
    self.assertIn('Phase wrong_phase doesn\'t exist', mbw.out)

    # Check that passing a correct phase key to a multi-phase builder passes.
    mbw = self.check(['lookup', '-m', 'fake_master', '-b', 'fake_multi_phase',
                      '--phase', 'phase_1'], ret=0)
    self.assertIn('phase = 1', mbw.out)

    mbw = self.check(['lookup', '-m', 'fake_master', '-b', 'fake_multi_phase',
                      '--phase', 'phase_2'], ret=0)
    self.assertIn('phase = 2', mbw.out)

  def test_validate(self):
    mbw = self.fake_mbw()
    self.check(['validate'], mbw=mbw, ret=0)

  def test_gyp_env_hacks(self):
    mbw = self.fake_mbw()
    mbw.files[mbw.default_config] = GYP_HACKS_CONFIG
    self.check(['lookup', '-c', 'fake_config'], mbw=mbw,
               ret=0,
               out=("GYP_DEFINES='foo=bar baz=1'\n"
                    "GYP_LINK_CONCURRENCY=1\n"
                    "LLVM_FORCE_HEAD_REVISION=1\n"
                    "python build/gyp_chromium -G output_dir=_path_\n"))


if __name__ == '__main__':
  unittest.main()