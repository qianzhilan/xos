import unittest
from xosgenx.generator import XOSGenerator
from helpers import FakeArgs, XProtoTestHelpers
import pdb

"""The function below is for eliminating warnings arising due to the missing policy_output_validator,
which is generated and loaded dynamically.
"""
def policy_output_validator(x, y):
    raise Exception("Validator not generated. Test failed.")
    return False

"""
The tests below use the Python code target to generate 
Python validation policies, set up an appropriate environment and execute the Python.
"""
class XProtoGeneralValidationTest(unittest.TestCase):
    def setUp(self):
        self.target = XProtoTestHelpers.write_tmp_target("{{ xproto_fol_to_python_validator('output', proto.policies.test_policy, None, 'Necessary Failure') }}")

    def test_constant(self):
        xproto = \
"""
    policy test_policy < False >
"""
        args = FakeArgs()
        args.inputs = xproto
        args.target = self.target

        output = XOSGenerator.generate(args)

        exec(output) # This loads the generated function, which should look like this:

        """
        def policy_output_validator(obj, ctx):
            i1 = False
            if (not i1):
                raise Exception('Necessary Failure')
        """

        with self.assertRaises(Exception):
           policy_output_validator({}, {})
    
    def test_equal(self):
        xproto = \
"""
    policy test_policy < not (ctx.user = obj.user) >
"""

        args = FakeArgs()
        args.inputs = xproto
        args.target = self.target

        output = XOSGenerator.generate(args)

        exec(output) # This loads the generated function, which should look like this:

        """
        def policy_output_validator(obj, ctx):
            i2 = (ctx.user == obj.user)
            i1 = (not i2)
            if (not i1):
                raise Exception('Necessary Failure')
        """

        obj = FakeArgs()
	obj.user = 1
        ctx = FakeArgs()
	ctx.user = 1

        with self.assertRaises(Exception):
           policy_output_validator(obj, ctx)

    def test_equal(self):
        xproto = \
"""
    policy test_policy < not (ctx.user = obj.user) >
"""

        args = FakeArgs()
        args.inputs = xproto
        args.target = self.target

        output = XOSGenerator.generate(args)

        exec(output) # This loads the generated function, which should look like this:

        """
        def policy_output_validator(obj, ctx):
            i2 = (ctx.user == obj.user)
            i1 = (not i2)
            if (not i1):
                raise Exception('Necessary Failure')
        """

        obj = FakeArgs()
	obj.user = 1
        ctx = FakeArgs()
	ctx.user = 1

        with self.assertRaises(Exception):
           policy_output_validator(obj, ctx)

    def test_bin(self):
        xproto = \
"""
    policy test_policy < (ctx.is_admin = True | obj.empty = True) & False>
"""

        args = FakeArgs()
        args.inputs = xproto
        args.target = self.target

        output = XOSGenerator.generate(args)
        exec(output) # This loads the generated function, which should look like this:

        """
        def policy_output_validator(obj, ctx):
            i2 = (ctx.is_admin == True)
            i3 = (obj.empty == True)
            i1 = (i2 or i3)
            if (not i1):
                raise Exception('Necessary Failure')
        """

        obj = FakeArgs()
	obj.empty = True

	ctx = FakeArgs()
	ctx.is_admin = True

        with self.assertRaises(Exception):
            verdict = policy_output_validator(obj, ctx)

        
    def test_exists(self):
        xproto = \
"""
    policy test_policy < exists Privilege: Privilege.object_id = obj.id >
"""
	args = FakeArgs()
        args.inputs = xproto
        args.target = self.target

        output = XOSGenerator.generate(args)
        exec(output) # This loads the generated function, which should look like this:

        """
        def policy_output_validator(obj, ctx):
            i1 = Privilege.objects.filter(Q(object_id=obj.id))[0]
            if (not i1):
                raise Exception('Necessary Failure')
        """

        self.assertTrue(policy_output_validator is not None)
	
    def test_python(self):
        xproto = \
"""
    policy test_policy < {{ "jack" in ["the", "box"] }} = True >
"""
	args = FakeArgs()
        args.inputs = xproto
        args.target = self.target
        output = XOSGenerator.generate(args)
        exec(output) # This loads the generated function, which should look like this:

        """
        def policy_output_validator(obj, ctx):
            i2 = ('jack' in ['the', 'box'])
            i1 = (i2 == True)
            if (not i1):
                raise Exception('Necessary Failure')
        """

        with self.assertRaises(Exception):
            self.assertTrue(policy_output_validator({}, {}) is True)

    def test_forall(self):
        # This one we only parse
        xproto = \
"""
    policy test_policy < forall Credential: Credential.obj_id = obj_id >
"""

        args = FakeArgs()
        args.inputs = xproto
        args.target = self.target

        output = XOSGenerator.generate(args)

        """
        def policy_output_enforcer(obj, ctx):
            i2 = Credential.objects.filter((~ Q(obj_id=obj_id)))[0]
            i1 = (not i2)
            return i1
        """

        self.assertIn('policy_output_validator', output)

if __name__ == '__main__':
    unittest.main()
